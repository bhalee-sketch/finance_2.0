"""계좌 이름/코드 검색, 자금이체 문구 및 로컬 생성 이력."""
from result_paths import result_path
from datetime import datetime
from pathlib import Path
import re
import sqlite3
from contextlib import closing
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment
from verifier import excel_rows


def find_accounts(settings):
    settings=Path(settings);folder=settings/'accounts'
    candidates=[]
    if folder.is_dir():
        candidates=[p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ('.xls','.xlsx','.xlsm') and not p.name.startswith('~$')]
    if settings.is_dir():
        candidates += [p for p in settings.iterdir() if p.is_file() and p.stem.lower()=='accounts' and p.suffix.lower() in ('.xls','.xlsx','.xlsm')]
    if len(candidates)!=1:
        raise ValueError(f'{folder} 폴더 또는 settings의 accounts Excel 파일을 확인하세요. 검색된 계좌목록: {len(candidates)}개. 자료 설정에서 파일을 직접 선택할 수 있습니다.')
    return candidates[0]


def load_accounts(path):
    path=Path(path)
    if path.suffix.lower() not in ('.xls','.xlsx','.xlsm'):raise ValueError('계좌목록은 .xls, .xlsx, .xlsm 파일이어야 합니다.')
    rows=excel_rows(path,1);columns=None;result=[]
    try:
        for index,row in enumerate(rows,1):
            if columns is None:
                headers=[re.sub(r'\s+','',str(v or '')) for v in row]
                names=('계좌명/코드','계좌명','통장명','예적금명')
                name=next((headers.index(h) for h in names if h in headers),None)
                account=next((headers.index(h) for h in ('계좌번호','이체계좌','출금계좌') if h in headers),None)
                if name is not None and account is not None:columns=(name,account);continue
                if index>=10:break
                continue
            ni,ai=columns
            name=str(row[ni] or '').strip() if ni<len(row) else ''
            if not name:continue
            value=row[ai] if ai<len(row) else None
            if isinstance(value,(int,float)) and value==int(value):value=int(value)
            result.append({'name':name,'number':str(value or '').strip(),'row':index})
    finally:rows.close()
    if columns is None:raise ValueError(f'{path.name}: 계좌명/코드(또는 통장명)와 계좌번호 열을 찾지 못했습니다.')
    if not result:raise ValueError(f'{path.name}: 계좌목록이 비어 있습니다.')
    return result


def matches(accounts,code):
    code=code.strip()
    if not code:return list(accounts)
    search=lambda text:[a for a in accounts if text.casefold() in a['name'].casefold()]
    if re.fullmatch(r'[0-9]{5}',code):
        return [a for a in accounts if re.sub(r'\D','',a['number']).endswith(code)
                or any(part.endswith(code) for part in re.findall(r'[0-9]+',a['name']))]
    if re.fullmatch(r'[0-9]{4}',code):
        padded=search('0'+code)
        if padded:return padded
    return search(code)


def make_text(prefix,source,destination):
    if not source or not destination:raise ValueError('출금계좌와 입금계좌를 각각 선택하세요.')
    text=f"{source['name']} -> {destination['name']}"
    return f'{prefix.strip()} : {text}' if prefix.strip() else text


def history_path(settings):
    return Path(settings)/'accounts'/'문구이력'/'history.sqlite3'


def append_history(db,from_code,to_code,text):
    db=Path(db);db.parent.mkdir(parents=True,exist_ok=True)
    now=datetime.now().isoformat(timespec='seconds')
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, created TEXT NOT NULL, from_code TEXT NOT NULL, to_code TEXT NOT NULL, text TEXT NOT NULL)')
        cursor=conn.execute('INSERT INTO history(created,from_code,to_code,text) VALUES(?,?,?,?)',(now,from_code,to_code,text))
        return cursor.lastrowid


def read_history(db,limit=200):
    db=Path(db)
    if not db.exists():return []
    with closing(sqlite3.connect(db)) as conn, conn:
        return conn.execute('SELECT id,created,from_code,to_code,text FROM history ORDER BY id DESC LIMIT ?',(limit,)).fetchall()


def export_history(db):
    records=read_history(db,2147483647)
    if not records:raise ValueError('저장된 생성 이력이 없습니다.')
    w=Workbook();s=w.active;s.title='생성이력'
    s.append(['생성일시','출금 코드','입금 코드','문구'])
    for record in reversed(records):
        s.append(list(record[1:]))
        for c in s[s.max_row]:c.data_type='s';c.alignment=Alignment(vertical='center',wrap_text=True)
    for c in s[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='24476B')
    for c,width in [('A',24),('B',24),('C',24),('D',100)]:s.column_dimensions[c].width=width
    s.freeze_panes='A2';s.auto_filter.ref=s.dimensions
    path=result_path('자금이체 문구 생성')
    w.save(path);w.close();return path


def resolve_account(accounts,query):
    query=query.strip()
    if not query:raise ValueError('계좌명 또는 코드를 입력하세요.')
    exact=[a for a in accounts if a['name'].casefold()==query.casefold()]
    found=exact or matches(accounts,query)
    if not found:raise ValueError('일치하는 계좌가 없습니다. 이름이나 코드를 확인하세요.')
    if len(found)>1:raise ValueError(f'{len(found)}개 계좌가 일치합니다. 계좌명이나 코드를 더 구체적으로 입력하세요.')
    return found[0]


def delete_history(db,ids):
    """선택한 이력만 삭제. 빈 선택은 전체 삭제를 의미하지 않는다."""
    ids=list({int(value) for value in ids})
    if not ids or not Path(db).exists():return 0
    with closing(sqlite3.connect(db)) as conn, conn:
        before=conn.total_changes
        conn.executemany('DELETE FROM history WHERE id=?',[(value,) for value in ids])
        return conn.total_changes-before


def clear_history(db):
    if not Path(db).exists():return 0
    with closing(sqlite3.connect(db)) as conn, conn:
        return conn.execute('DELETE FROM history').rowcount
