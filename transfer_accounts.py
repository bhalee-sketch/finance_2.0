"""Versioned monthly transfer account imports matching the supplied reference."""
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,sqlite3,re
from pathlib import Path
from verifier import excel_rows
from transfer_text import load_accounts
from account_verifier import account_key

DATABASE=Path(__file__).resolve().parent/'data'/'transfer'/'accounts.sqlite3'


def normalize_source(source):
    stream=excel_rows(source,1)
    try:
        headers=[re.sub(r'\s+','',str(value or '')) for value in next(stream,[])]
        if not {'관리부서','예적금명','계좌번호'}.issubset(headers):
            if {'예금종류','사용여부','예적금코드'}&set(headers):raise ValueError('원본의 관리부서·예적금명·계좌번호 열을 확인하세요.')
            return load_accounts(source),{}
        accounts=[];excluded=Counter()
        for source_row,values in enumerate(stream,2):
            row={name:values[i] if i<len(values) else None for i,name in enumerate(headers)}
            if not any(value is not None and str(value).strip() for value in values):continue
            department=str(row.get('관리부서') or '').strip()
            if department in ('법인팀','복지회'):excluded[department]+=1;continue
            name=str(row.get('예적금명') or '').strip();number=row.get('계좌번호')
            if isinstance(number,(int,float)) and number==int(number):number=str(int(number))
            number=str(number or '').strip()
            if not name or not account_key(number):raise ValueError(f'{source_row}행의 계좌명·계좌번호를 확인하세요.')
            accounts.append({'name':name,'number':number,'row':source_row})
        if not accounts:raise ValueError('사용할 자금이체 계좌가 없습니다.')
        accounts.sort(key=lambda account:account['number'])
        return accounts,dict(excluded)
    finally:stream.close()


def read_accounts(database=DATABASE):
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True) as connection:
        return [{'name':name,'number':number,'row':row} for name,number,row in connection.execute(
            'SELECT a.name,a.number,a.source_row FROM accounts a JOIN active v ON v.import_id=a.import_id ORDER BY a.position')]


def import_accounts(source,database=DATABASE):
    source,database=Path(source),Path(database)
    accounts,excluded=normalize_source(source);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    database.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY,filename TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE,
                imported_at TEXT NOT NULL,account_count INTEGER NOT NULL,excluded_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts(import_id INTEGER NOT NULL REFERENCES imports(id),position INTEGER NOT NULL,
                name TEXT NOT NULL,number TEXT NOT NULL,source_row INTEGER NOT NULL,PRIMARY KEY(import_id,position));
            CREATE TABLE IF NOT EXISTS active(id INTEGER PRIMARY KEY CHECK(id=1),import_id INTEGER NOT NULL REFERENCES imports(id));
        ''')
        existing=connection.execute('SELECT id FROM imports WHERE sha256=?',(digest,)).fetchone()
        if existing:import_id=existing[0]
        else:
            import_id=connection.execute('INSERT INTO imports(filename,sha256,imported_at,account_count,excluded_json) VALUES(?,?,?,?,?)',
                (source.name,digest,datetime.now(timezone.utc).isoformat(),len(accounts),json.dumps(excluded,ensure_ascii=False))).lastrowid
            connection.executemany('INSERT INTO accounts VALUES(?,?,?,?,?)',
                ((import_id,position,item['name'],item['number'],item['row']) for position,item in enumerate(accounts)))
        connection.execute('INSERT OR REPLACE INTO active VALUES(1,?)',(import_id,))
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('이체계좌 DB 무결성 오류')
    if read_accounts(database)!=accounts:raise ValueError('자금이체 계좌 원본과 DB가 일치하지 않습니다.')
    return {'source':source.name,'sha256':digest,'accounts':len(accounts),'excluded':excluded,
            'verification':'All normalized account names and numbers match the database'}
