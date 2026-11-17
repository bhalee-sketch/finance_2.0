"""Read bundled financial statements from SQLite without the original Excel files."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from openpyxl import Workbook


DATABASE = Path(__file__).resolve().parent / 'data' / 'statements' / 'statements.sqlite3'


@dataclass(frozen=True)
class StatementSource:
    database: Path
    year: str

    @property
    def parent(self):
        return self.database.parent


def connect(database):
    return sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)


def discover_statements(database=DATABASE):
    database = Path(database)
    if not database.exists():
        return {}
    with connect(database) as connection:
        return {str(year): StatementSource(database, str(year)) for year, in connection.execute(
            'SELECT fiscal_year FROM workbooks ORDER BY fiscal_year DESC')}


def decode(value):
    value = json.loads(value)
    if isinstance(value, dict):
        constructors = {'date': date, 'datetime': datetime, 'time': time}
        return constructors[value['type']].fromisoformat(value['value'])
    return value


def read_workbook(source):
    workbook = Workbook()
    workbook.remove(workbook.active)
    try:
        with connect(source.database) as connection:
            sheets = connection.execute(
                'SELECT s.id,s.name,s.row_count,s.column_count,s.merged_ranges_json '
                'FROM sheets s JOIN workbooks w ON w.id=s.workbook_id '
                'WHERE w.fiscal_year=? ORDER BY s.position', (source.year,)).fetchall()
            if not sheets:
                raise ValueError(f'{source.year}년 재무제표가 DB에 없습니다.')
            for sheet_id, name, rows, columns, merged in sheets:
                sheet = workbook.create_sheet(name)
                sheet.cell(rows, columns)  # Retain the original extent, including blank cells.
                for row, column, value, kind, fmt in connection.execute(
                    'SELECT row_number,column_number,cached_value_json,excel_type,number_format '
                    'FROM cells WHERE sheet_id=?', (sheet_id,)):
                    cell = sheet.cell(row, column, decode(value))
                    if kind in ('s', 'e', 'b', 'n'):
                        cell.data_type = kind
                    cell.number_format = fmt
                for bounds in json.loads(merged):
                    sheet.merge_cells(bounds)
        return workbook
    except Exception:
        workbook.close()
        raise


def load_record(source):
    from statement_loader import _read_sheet
    workbook = read_workbook(source)
    try:
        return {'sheets': [_read_sheet(sheet) for sheet in workbook]}
    finally:
        workbook.close()


@contextmanager
def export_source(source):
    """Supply the existing full-year formatter with a temporary DB snapshot."""
    with TemporaryDirectory(prefix='workspace-statement-') as folder:
        path = Path(folder) / f'{source.year}회계연도.xlsx'
        workbook = read_workbook(source)
        try:
            workbook.save(path)
        finally:
            workbook.close()
        yield path
