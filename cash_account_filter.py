"""Extract ledger transactions classified under the fiscal year's cash statement."""
from contextlib import closing
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from finance_data import excel_safe_text, money, rows, save_atomic, text
from resource_cashflow import account_catalog, match_cash_account
from statement_analysis import normalize


def filter_cash_accounts(source, target, history):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError('결과 파일은 원본과 다른 이름으로 저장하세요.')
    with closing(rows(source)) as stream:
        headers = next(stream, [])
        names = [text(v) for v in headers]
        required = ('년도', '관', '항', '목', '차변', '대변')
        invalid = [name for name in required if names.count(name) != 1]
        if invalid:
            raise ValueError('첫 시트의 첫 행에서 누락되거나 중복된 열을 확인하세요. ' + ', '.join(invalid))
        year_col, kwan, hang, mok, debit, credit = (names.index(name) for name in required)
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet('자금계산서 계정')
        sheet.freeze_panes = 'A2'
        header_cells = []
        for col, value in enumerate(headers, 1):
            letter = get_column_letter(col)
            sheet.column_dimensions[letter].width = 48 if value == '적요' else 19
            cell = WriteOnlyCell(sheet, value=excel_safe_text(value))
            if isinstance(value, str):
                cell.data_type = 's'
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='244C70')
            header_cells.append(cell)
        scanned = kept = 0
        catalogs = {}
        try:
            sheet.append(header_cells)
            for line, row in enumerate(stream, 2):
                if not any(v is not None and v != '' for v in row):
                    continue
                if any(text(v) for v in row[len(headers):]):
                    raise ValueError(f'{line}행에 열 제목이 없는 데이터가 있습니다.')
                row = row[:len(headers)] + [None] * max(0, len(headers) - len(row))
                year = text(row[year_col])
                if year not in catalogs:
                    if len(year) != 4 or not year.isascii() or not year.isdigit():
                        raise ValueError(f'{line}행의 회계연도를 확인하세요.')
                    basis = max((y for y in history if y <= year), default=None)
                    if not basis:
                        raise ValueError(f'{year}회계연도에 적용할 자금계산서가 없습니다.')
                    catalog, _ = account_catalog(history[basis])
                    if not catalog:
                        raise ValueError(f'{basis}회계연도 자금계산서 계정표가 비어 있습니다.')
                    catalogs[year] = catalog
                scanned += 1
                account = tuple(normalize(row[c]) for c in (kwan, hang, mok))
                sides, purchase = match_cash_account(catalogs[year], account)
                if not sides:
                    continue
                if purchase and ('지출' not in sides or not money(row[debit]) or money(row[credit])):
                    continue
                cells = []
                for i, value in enumerate(row):
                    cell = WriteOnlyCell(sheet, value=excel_safe_text(value))
                    if isinstance(value, str):
                        cell.data_type = 's'
                    elif i in (debit, credit) and isinstance(value, (float, int)):
                        cell.number_format = '#,##0.##########' if value != int(value) else '#,##0'
                    cells.append(cell)
                sheet.append(cells)
                kept += 1
            sheet.auto_filter.ref = f'A1:{get_column_letter(len(headers))}{kept + 1}'
            save_atomic(workbook, target)
        finally:
            # A rejected input can leave openpyxl's streamed worksheet XML on disk.
            if not sheet.closed:
                sheet.close()
            if sheet._writer and Path(sheet._writer.out).exists():
                sheet._writer.cleanup()
            workbook.close()
    return target, scanned, kept
