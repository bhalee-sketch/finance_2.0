"""Persistent account ledger, retaining all original columns and exact amounts."""
from collections import defaultdict
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zlib

from finance_data import LEDGER_COLUMNS, rows, text, money, date_text

DATABASE = Path(__file__).resolve().parent / 'data' / 'ledgers' / 'ledgers.sqlite3'


def registered_database(settings):
    return Path(settings) / '계정별원장.sqlite3'


def read_connection(database):
    return sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)


def discover_years(database=None):
    databases = (DATABASE, *sorted(DATABASE.parent.glob('ledgers-*.sqlite3'))) if database is None else (Path(database),)
    years = {}
    for path in databases:
        if path.is_file():
            with closing(read_connection(path)) as connection:
                for year, in connection.execute('SELECT fiscal_year FROM imports'):
                    if year in years:raise ValueError(f'{year}회계연도 내장 원장이 중복됩니다.')
                    years[year] = path
    return dict(sorted(years.items(), reverse=True))


def encode(row):
    return json.dumps(row, ensure_ascii=False, default=lambda value: value.isoformat(), allow_nan=False)


def source_records(source):
    stream = rows(source)
    try:
        headers = [text(v) for v in next(stream, [])]
        if any(headers.count(c) != 1 for c in LEDGER_COLUMNS):
            raise ValueError('원장 열 제목이 중복되거나 필수 열이 없습니다.')
        for number, values in enumerate(stream, 2):
            if not any(text(v) for v in values):continue
            raw = dict(zip(headers, values))
            record = {c: str(money(raw.get(c))) if c in ('차변', '대변') else
                      date_text(raw.get(c)) if c == '회계일자' else text(raw.get(c)) for c in LEDGER_COLUMNS}
            yield number, record, [values[i] if i < len(values) else None for i in range(len(headers))], headers
    finally:
        stream.close()


def import_ledger(source, year, database=DATABASE, *, allow_replace=False):
    source, database = Path(source), Path(database)
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS imports(fiscal_year TEXT PRIMARY KEY,filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,headers_json TEXT NOT NULL,row_count INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS entries(fiscal_year TEXT NOT NULL REFERENCES imports(fiscal_year),
                source_row INTEGER NOT NULL,payload BLOB NOT NULL,raw_json BLOB NOT NULL,
                PRIMARY KEY(fiscal_year,source_row));
        ''')
        if not any(column[1]=='raw_json' for column in connection.execute('PRAGMA table_info(entries)')):
            raise ValueError('배포용 원장 DB입니다. 원본 검증과 가져오기는 저장소의 전체 원장 DB에서 실행하세요.')
        with connection:
            connection.execute('BEGIN IMMEDIATE')
            existing = connection.execute('SELECT sha256 FROM imports WHERE fiscal_year=?', (str(year),)).fetchone()
            if existing and existing[0] != digest:
                if not allow_replace:raise ValueError('같은 연도의 다른 원장이 있어 덮어쓰지 않습니다.')
                connection.execute('DELETE FROM entries WHERE fiscal_year=?', (str(year),))
                connection.execute('DELETE FROM imports WHERE fiscal_year=?', (str(year),))
                existing = None
            count = 0; totals = defaultdict(Decimal); headers = []; payload_digest = hashlib.sha256()
            if not existing:
                connection.execute('INSERT INTO imports VALUES(?,?,?,?,0)', (str(year), source.name, digest, '[]'))
            for number, record, raw, headers in source_records(source):
                fiscal_year = re.fullmatch(r'(20\d{2})(?:회계연도|년도|년)?', record['년도'])
                if record['년도'] and (not fiscal_year or fiscal_year[1] != str(year)):
                    raise ValueError(f"{number}행의 년도({record['년도']})가 등록 연도({year})와 다릅니다.")
                payload = zlib.compress(encode([record[c] for c in LEDGER_COLUMNS]).encode())
                raw_json = zlib.compress(encode(raw).encode())
                payload_digest.update(str(number).encode()+payload+raw_json)
                if not existing:connection.execute('INSERT INTO entries VALUES(?,?,?,?)', (str(year), number, payload, raw_json))
                count += 1
                for c in ('차변', '대변'):totals[c] += Decimal(record[c])
            if not count:raise ValueError('등록할 원장 거래가 없습니다.')
            if not existing:
                connection.execute('UPDATE imports SET headers_json=?,row_count=? WHERE fiscal_year=?', (encode(headers), count, str(year)))
            db_digest = hashlib.sha256(); db_count = 0; db_totals = defaultdict(Decimal)
            for number, payload, raw in connection.execute('SELECT source_row,payload,raw_json FROM entries WHERE fiscal_year=? ORDER BY source_row', (str(year),)):
                db_digest.update(str(number).encode()+payload+raw); db_count += 1
                values=dict(zip(LEDGER_COLUMNS,json.loads(zlib.decompress(payload))))
                for c in ('차변', '대변'):db_totals[c] += Decimal(values[c])
            if (count, dict(totals), payload_digest.hexdigest()) != (db_count, dict(db_totals), db_digest.hexdigest()):
                raise ValueError('원본과 DB 검증이 일치하지 않습니다.')
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':raise ValueError('DB 무결성 오류')
        return {'year':str(year), 'rows':count, 'columns':headers, 'sha256':digest,
                'totals':{c:str(v) for c,v in totals.items()}, 'verification':'All normalized and original row values match database; exact debit/credit totals match'}
    finally:
        connection.close()


def load_records(database, year):
    return list(iter_records(database, year))


def iter_records(database, year, *, with_provenance=False, subject=None):
    if subject is not None:
        from statement_analysis import normalize
        subject_column=LEDGER_COLUMNS.index('목')
    with closing(read_connection(database)) as connection:
        for number, payload in connection.execute(
                'SELECT source_row,payload FROM entries WHERE fiscal_year=? ORDER BY source_row', (str(year),)):
            values=json.loads(zlib.decompress(payload))
            if subject is not None and normalize(values[subject_column])!=subject:continue
            record = dict(zip(LEDGER_COLUMNS,values))
            for key in ('차변', '대변'):record[key] = Decimal(record[key])
            if with_provenance:record.update(_source_file=str(database),_source_row=number)
            yield record


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path); parser.add_argument('--year', required=True)
    parser.add_argument('--database', type=Path, default=DATABASE)
    args = parser.parse_args()
    print(json.dumps(import_ledger(args.source,args.year,args.database),ensure_ascii=False,indent=2))
