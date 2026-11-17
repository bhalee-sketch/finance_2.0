"""Normalize monthly deposit exports and retain versioned account snapshots."""
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from account_verifier import account_key
from deposit_plan import read_catalog
from verifier import excel_rows,number

DATABASE=Path(__file__).resolve().parent/'data'/'deposit'/'fixed_accounts.sqlite3'
BANKS={'KEB하나은행':'하나','하나은행':'하나','한국교직원공제회':'공제회','국민은행':'국민',
       '기업은행':'기업','농협은행(주)':'농협','농협회원조합':'농협','신한은행':'신한'}


def normalize_source(source):
    stream=excel_rows(source,1)
    try:
        header=[str(value or '').strip() for value in next(stream,[])]
        if not {'예금종류','사용여부','계약금액','계좌번호','회계단위','예치기관','예적금명','해약일'}.issubset(header):
            return read_catalog(source,True),{}
        if len(header)!=len(set(header)):raise ValueError('원본의 열 제목이 중복됩니다.')
        result={};excluded=Counter()
        for row_number,values in enumerate(stream,2):
            row={name:values[i] if i<len(values) else None for i,name in enumerate(header)}
            text=lambda key:str(row.get(key) or '').strip()
            if not any(value is not None and str(value).strip() for value in values):continue
            if text('예금종류')!='정기예금':excluded['정기예금 외']+=1;continue
            if text('사용여부')!='사용':excluded['사용 중 아님']+=1;continue
            unit=re.sub(r'^\d+\s*','',text('회계단위'))
            if unit=='법인':excluded['법인 계좌']+=1;continue
            if re.search(r'\d',text('해약일')):excluded['해약 계좌']+=1;continue
            if not text('계약금액'):excluded['원금 없음']+=1;continue
            principal=number(row['계약금액'])
            if principal<0:raise ValueError(f'{row_number}행의 원금이 음수입니다.')
            if principal==0:excluded['원금 0원']+=1;continue
            raw=row.get('계좌번호')
            account=str(int(raw)) if isinstance(raw,(int,float)) and raw==int(raw) else text('계좌번호')
            key=account_key(account)
            if not key:raise ValueError(f'{row_number}행의 계좌번호를 확인하세요.')
            if key in result:raise ValueError(f'{row_number}행의 계좌가 중복됩니다.')
            if not unit or not text('예치기관') or not text('예적금명'):raise ValueError(f'{row_number}행의 은행·회계단위·계좌명을 확인하세요.')
            result[key]={'account':account,'bank':BANKS.get(text('예치기관'),text('예치기관')),
                         'unit':unit.replace('비등록금','비'),'name':text('예적금명'),
                         'principal':principal,'maturity':text('만기일')}
        if not result:raise ValueError('사용 가능한 정기예금 계좌가 없습니다.')
        return result,dict(excluded)
    finally:stream.close()


def load_fixed_accounts(database=DATABASE):
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True) as connection:
        return {key:{'account':account,'bank':bank,'unit':unit,'name':name,'principal':Decimal(principal),'maturity':maturity}
                for key,account,bank,unit,name,principal,maturity in connection.execute(
                    'SELECT a.account_key,a.account,a.bank,a.unit,a.name,a.principal,a.maturity FROM accounts a JOIN active v ON v.import_id=a.import_id ORDER BY a.position')}


def import_fixed_accounts(source,database=DATABASE):
    source,database=Path(source),Path(database)
    accounts,excluded=normalize_source(source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    database.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY,filename TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE,
                imported_at TEXT NOT NULL,account_count INTEGER NOT NULL,excluded_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts(import_id INTEGER NOT NULL REFERENCES imports(id),account_key TEXT NOT NULL,
                position INTEGER NOT NULL,account TEXT NOT NULL,bank TEXT NOT NULL,unit TEXT NOT NULL,name TEXT NOT NULL,
                principal TEXT NOT NULL,maturity TEXT NOT NULL,PRIMARY KEY(import_id,account_key));
            CREATE TABLE IF NOT EXISTS active(id INTEGER PRIMARY KEY CHECK(id=1),import_id INTEGER NOT NULL REFERENCES imports(id));
        ''')
        existing=connection.execute('SELECT id FROM imports WHERE sha256=?',(digest,)).fetchone()
        if existing:import_id=existing[0]
        else:
            import_id=connection.execute('INSERT INTO imports(filename,sha256,imported_at,account_count,excluded_json) VALUES(?,?,?,?,?)',
                (source.name,digest,datetime.now(timezone.utc).isoformat(),len(accounts),json.dumps(excluded,ensure_ascii=False))).lastrowid
            connection.executemany('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?,?)',
                ((import_id,key,position,item['account'],item['bank'],item['unit'],item['name'],str(item['principal']),item.get('maturity',''))
                 for position,(key,item) in enumerate(accounts.items())))
        connection.execute('INSERT OR REPLACE INTO active VALUES(1,?)',(import_id,))
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('정기예금 DB 무결성 오류')
    stored=load_fixed_accounts(database)
    for key,item in accounts.items():
        if any(stored[key].get(field)!=value for field,value in item.items()):raise ValueError('정기예금 DB 대조 오류')
    return {'source':source.name,'sha256':digest,'accounts':len(accounts),'excluded':excluded,
            'principal_total':str(sum((item['principal'] for item in accounts.values()),Decimal(0))),
            'verification':'Normalized account data matches the database'}
