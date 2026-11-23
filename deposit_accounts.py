"""Bundled principal transfer accounts for the deposit termination plan."""
from pathlib import Path
import hashlib
import json
import sqlite3
from deposit_plan import read_catalog

DATABASE=Path(__file__).resolve().parent/'data'/'deposit'/'regular_accounts.sqlite3'


def load_accounts(database=DATABASE):
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True) as connection:
        return {key:{'account':account,'bank':bank,'name':name}
                for key,account,bank,name in connection.execute('SELECT account_key,account,bank,name FROM accounts ORDER BY position')}


def import_accounts(source,database=DATABASE,*,replace=False):
    source,database=Path(source),Path(database)
    accounts=read_catalog(source,False)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    return store_accounts(database,accounts,source.name,digest,replace=replace)


def store_accounts(database,accounts,filename,digest=None,*,replace=False):
    if digest is None:
        digest=hashlib.sha256(json.dumps(accounts,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    database.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS imports(filename TEXT NOT NULL,sha256 TEXT NOT NULL,account_count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts(account_key TEXT PRIMARY KEY,position INTEGER NOT NULL UNIQUE,
                account TEXT NOT NULL,bank TEXT NOT NULL,name TEXT NOT NULL);
        ''')
        existing=connection.execute('SELECT sha256 FROM imports').fetchone()
        if existing and existing[0]!=digest:
            if not replace:raise ValueError('다른 계좌 자료가 이미 저장되어 있어 덮어쓰지 않습니다.')
            connection.execute('DELETE FROM accounts')
            connection.execute('DELETE FROM imports')
            existing=None
        if not existing:
            connection.execute('INSERT INTO imports VALUES(?,?,?)',(filename,digest,len(accounts)))
            connection.executemany('INSERT INTO accounts VALUES(?,?,?,?,?)',
                ((key,index,record['account'],record['bank'],record['name']) for index,(key,record) in enumerate(accounts.items())))
        stored={key:{'account':account,'bank':bank,'name':name} for key,account,bank,name in connection.execute('SELECT account_key,account,bank,name FROM accounts ORDER BY position')}
        if stored!=accounts:raise ValueError('계좌 원본과 DB가 일치하지 않습니다.')
        if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('계좌 DB 무결성 오류')
    return {'source':filename,'sha256':digest,'accounts':len(accounts),'verification':'All account numbers, banks and account names match the original; integrity check passed'}
