"""Import an Excel workbook without dropping headers, empty rows or cell types.

Usage: python scripts/import_statement_db.py FILE.xlsx DB.sqlite3 --year 2025
Original Excel formatting remains available in the separately retained workbook.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from openpyxl import load_workbook


def encode(value):
    if isinstance(value, (datetime, date, time)):
        return json.dumps({'type': type(value).__name__, 'value': value.isoformat()})
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def import_workbook(source, database, year):
    source, database = Path(source), Path(database)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    database.parent.mkdir(parents=True, exist_ok=True)
    workbook = load_workbook(source, data_only=False)
    cached = load_workbook(source, data_only=True)
    connection = sqlite3.connect(database)
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS workbooks (
                id INTEGER PRIMARY KEY, fiscal_year INTEGER NOT NULL UNIQUE,
                filename TEXT NOT NULL, sha256 TEXT NOT NULL, imported_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sheets (
                id INTEGER PRIMARY KEY, workbook_id INTEGER NOT NULL REFERENCES workbooks(id),
                position INTEGER NOT NULL, name TEXT NOT NULL,
                row_count INTEGER NOT NULL, column_count INTEGER NOT NULL,
                merged_ranges_json TEXT NOT NULL, UNIQUE(workbook_id, name));
            CREATE TABLE IF NOT EXISTS cells (
                sheet_id INTEGER NOT NULL REFERENCES sheets(id),
                row_number INTEGER NOT NULL, column_number INTEGER NOT NULL,
                value_json TEXT NOT NULL, cached_value_json TEXT NOT NULL,
                excel_type TEXT NOT NULL, number_format TEXT NOT NULL,
                PRIMARY KEY(sheet_id, row_number, column_number));
        ''')
        with connection:
            existing = connection.execute(
                'SELECT id, sha256 FROM workbooks WHERE fiscal_year=?', (year,)
            ).fetchone()
            if existing and existing[1] != digest:
                raise ValueError(f'{year} already contains a different workbook; refusing to overwrite')
            if existing:
                workbook_id = existing[0]
            else:
                workbook_id = connection.execute(
                    'INSERT INTO workbooks(fiscal_year, filename, sha256, imported_at) VALUES(?,?,?,?)',
                    (year, source.name, digest, datetime.now(timezone.utc).isoformat())
                ).lastrowid
                for position, sheet in enumerate(workbook):
                    sheet_id = connection.execute(
                        'INSERT INTO sheets(workbook_id,position,name,row_count,column_count,merged_ranges_json) '
                        'VALUES(?,?,?,?,?,?)',
                        (workbook_id, position, sheet.title, sheet.max_row, sheet.max_column,
                         json.dumps([str(r) for r in sheet.merged_cells.ranges]))
                    ).lastrowid
                    connection.executemany('INSERT INTO cells VALUES(?,?,?,?,?,?,?)', (
                        (sheet_id, cell.row, cell.column, encode(cell.value),
                         encode(cached[sheet.title].cell(cell.row, cell.column).value),
                         cell.data_type, cell.number_format)
                        for row in sheet for cell in row if cell.value is not None
                    ))

            # Compare every coordinate, including blanks, and every numeric column total.
            report = []
            for position, sheet in enumerate(workbook):
                stored = connection.execute(
                    'SELECT id,row_count,column_count FROM sheets WHERE workbook_id=? AND position=? AND name=?',
                    (workbook_id, position, sheet.title)
                ).fetchone()
                assert stored and stored[1:] == (sheet.max_row, sheet.max_column)
                values = {(r, c): (v, cache, kind, fmt) for r, c, v, cache, kind, fmt in connection.execute(
                    'SELECT row_number,column_number,value_json,cached_value_json,excel_type,number_format '
                    'FROM cells WHERE sheet_id=?', (stored[0],))}
                original_totals, db_totals = defaultdict(Decimal), defaultdict(Decimal)
                count = 0
                for row in sheet:
                    for cell in row:
                        saved = values.get((cell.row, cell.column))
                        if cell.value is None:
                            assert saved is None
                            continue
                        count += 1
                        assert saved == (encode(cell.value), encode(cached[sheet.title].cell(cell.row, cell.column).value),
                                         cell.data_type, cell.number_format), (sheet.title, cell.coordinate)
                        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                            original_totals[cell.column] += Decimal(str(cell.value))
                            db_totals[cell.column] += Decimal(str(json.loads(saved[0])))
                assert count == len(values)
                assert original_totals == db_totals
                report.append({'sheet': sheet.title, 'rows_including_header': sheet.max_row,
                               'columns': sheet.max_column, 'nonempty_cells': count,
                               'numeric_column_totals': {str(k): str(v) for k, v in db_totals.items()}})
            assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not connection.execute('PRAGMA foreign_key_check').fetchall()
        return {'fiscal_year': year, 'source_sha256': digest, 'sheets': report,
                'verification': 'All cell values, cached values, types, number formats and numeric column totals match'}
    finally:
        connection.close()
        workbook.close()
        cached.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('database', type=Path)
    parser.add_argument('--year', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(import_workbook(args.source, args.database, args.year), ensure_ascii=False, indent=2))
