"""원장 전용 로컬 캐시. 원본 SHA-256 검증, Decimal 문자열 저장, 원본 불변."""
from collections import OrderedDict
from decimal import Decimal,InvalidOperation
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import tempfile
import threading

VERSION=2
_memory=OrderedDict()
_lock=threading.RLock()


def fingerprint(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def cache_folder():
    if os.name=='nt' and os.environ.get('LOCALAPPDATA'):
        base=Path(os.environ['LOCALAPPDATA'])/'Settlement'/'ledger-cache'
    else:
        user=hashlib.sha256(str(Path.home()).encode()).hexdigest()[:16]
        base=Path(tempfile.gettempdir())/f'settlement-ledger-{user}'
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    return base


def cache_path(path):return cache_folder()/(hashlib.sha256(str(path).encode()).hexdigest()+'.sqlite3')


def read_disk(path,signature,columns):
    con=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        metadata=con.execute('SELECT version,signature,count,digest FROM metadata').fetchone()
        if metadata is None or metadata[:2]!=(VERSION,signature):return None
        records=[];digest=hashlib.sha256()
        for (payload,) in con.execute('SELECT payload FROM records ORDER BY position'):
            digest.update(payload.encode('utf-8'))
            values=json.loads(payload)
            if len(values)!=len(columns)+1:raise ValueError('캐시 열 불일치')
            row=dict(zip(columns,values[:-1]));row['_source_row']=values[-1]
            for key in ('차변','대변'):
                row[key]=Decimal(row[key])
                if not row[key].is_finite():raise ValueError('캐시 금액 오류')
            records.append(row)
        if len(records)!=metadata[2] or digest.hexdigest()!=metadata[3]:raise ValueError('캐시 내용 불일치')
        return records
    finally:con.close()


def write_disk(path,signature,records,columns):
    fd,tmp=tempfile.mkstemp(dir=path.parent,suffix='.sqlite3');os.close(fd)
    con=None
    try:
        con=sqlite3.connect(tmp)
        con.execute('CREATE TABLE metadata(version INTEGER,signature TEXT,count INTEGER,digest TEXT)')
        con.execute('CREATE TABLE records(position INTEGER PRIMARY KEY,payload TEXT NOT NULL)')
        digest=hashlib.sha256()
        def payloads():
            for i,row in enumerate(records):
                payload=json.dumps([str(row[k]) if isinstance(row[k],Decimal) else row[k] for k in columns]+[row['_source_row']],ensure_ascii=False)
                digest.update(payload.encode('utf-8'));yield i,payload
        con.executemany('INSERT INTO records VALUES (?,?)',payloads())
        con.execute('INSERT INTO metadata VALUES (?,?,?,?)',(VERSION,signature,len(records),digest.hexdigest()))
        con.commit();con.close();con=None;os.replace(tmp,path)
    finally:
        if con:con.close()
        if os.path.exists(tmp):os.unlink(tmp)


def load(path,columns,reader,with_provenance=False):
    path=Path(path).resolve()
    # 동시에 열린 메뉴의 중복 변환을 막고 반환 사전은 복사한다.
    with _lock:
        signature=fingerprint(path);key=(str(path),signature,VERSION)
        records=_memory.get(key)
        destination=None
        if records is None:
            try:
                destination=cache_path(path)
                if destination.exists():records=read_disk(destination,signature,columns)
            except (OSError,sqlite3.Error,ValueError,TypeError,KeyError,InvalidOperation):records=None
            if records is None:
                records=reader(path,with_provenance=True)
                if fingerprint(path)!=signature:raise ValueError('읽는 동안 원장 파일이 변경되었습니다. 저장 완료 후 다시 조회하세요.')
                if destination:
                    try:write_disk(destination,signature,records,columns)
                    except (OSError,sqlite3.Error):pass
            elif fingerprint(path)!=signature:raise ValueError('읽는 동안 원장 파일이 변경되었습니다. 다시 조회하세요.')
            _memory.clear();_memory[key]=records
        result=[]
        for original in records:
            row=original.copy()
            if with_provenance:row['_source_file']=str(path)
            else:
                row.pop('_source_file',None);row.pop('_source_row',None)
            result.append(row)
        return result
