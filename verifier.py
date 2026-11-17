"""첨부 VBA의 월별/기간별 거래처 합산 검증. 원본 파일은 읽기 전용."""
from result_paths import result_path
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime
import re
import io
from copy import copy
import unicodedata
import xlrd
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

PERIODS = {'1기 예정': (1,2,3), '1기 확정': (4,5,6), '2기 예정': (7,8,9), '2기 확정': (10,11,12)}
KINDS = ('매입세금계산서','매입계산서','매출세금계산서','매출계산서')
# 사용자 제공 통합 문서1.xlsx의 A:O 열 너비. D:F, I:N 묶음도 펼쳐 적용한다.
TAX_INVOICE_WIDTHS = ((90-5)/7,14.75,33.625,13.125,13.125,13.125,13.25,
                      28.75,13.125,13.125,13.125,13.125,13.125,13.125,11.25)

def key(value):
    raw = str(value or '')
    digits = ''.join(re.findall(r'[0-9]', raw))
    return ('P:' + digits[:6] if '*' in raw else 'E:' + digits) if digits else ''

def number(value):
    if value is None or str(value).strip() == '': return Decimal(0)
    try:
        result = Decimal(str(value).replace(',', '').strip())
        if not result.is_finite(): raise InvalidOperation
        return result
    except InvalidOperation:
        raise ValueError('숫자로 읽을 수 없는 금액이 있습니다. 원본 금액 셀을 확인하세요.')

def _enable_extended_legacy_rows(wb):
    """일부 학사 BIFF5 내보내기는 16-bit 행 번호 전체를 사용한다.

    이 워크북 인스턴스만 확장한다. BIFF 파싱 버전과 전역 xlrd는 변경하지 않는다.
    """
    if wb.biff_version not in (50, 70):
        return wb
    from types import MethodType
    from xlrd.biffh import XL_WORKSHEET
    from xlrd.sheet import Sheet
    def get_sheet(book, index, update_pos=True):
        if book._resources_released:
            raise xlrd.XLRDError('이미 닫힌 XLS 파일입니다.')
        if update_pos:
            book._position = book._sh_abs_posn[index]
        book.getbof(XL_WORKSHEET)
        sheet = Sheet(book, book._position, book._sheet_names[index], index)
        sheet.utter_max_rows = 65536
        sheet.read(book)
        book._sheet_list[index] = sheet
        return sheet
    wb.get_sheet = MethodType(get_sheet, wb)
    return wb


def open_legacy_workbook(path):
    wb = _enable_extended_legacy_rows(xlrd.open_workbook(str(path), on_demand=True, logfile=io.StringIO()))
    # 구형 학사 내보내기는 CODEPAGE를 생략한다. Unicode XLS와 명시된 인코딩은 유지한다.
    if wb.biff_version < 80 and wb.codepage is None:
        candidate = None
        try:
            candidate = _enable_extended_legacy_rows(xlrd.open_workbook(str(path), on_demand=True, encoding_override='cp949', logfile=io.StringIO()))
            ws = candidate.sheet_by_index(0)
            expected = {'사업자번호', '사업자등록번호', '거래처명', '공급가액', '발생금액', '계좌번호', '전일잔액', '현재잔액', '입금', '출금', '은행명', '통장명', '계좌명/코드', '계좌명', '출금계좌', '이체계좌', '원금', '회계단위'}
            headers = {str(v).replace(' ', '').strip() for r in range(min(ws.nrows, 10)) for v in ws.row_values(r)}
            # 기부금 등 새 업무의 열 제목도 인식한다. 특정 업무의 제목 목록에만
            # 의존하면 유효한 CP949 자료가 서유럽 문자로 읽혀 분류가 실패한다.
            korean_headers = {v for v in headers if re.search(r'[가-힣]{2,}', v)
                              and len(re.findall(r'[가-힣]', v)) >= len(v) / 2}
            if len(headers & expected) >= 2 or len(korean_headers) >= 2:
                wb.release_resources()
                return candidate
        except (UnicodeError, xlrd.XLRDError):
            pass
        if candidate is not None:
            candidate.release_resources()
    return wb


def summary_row(scope, kind, rows):
    needs_review = sum(r[-1] in ('차이', '확인필요') or r[0] in ('홈택스만', '학사만') for r in rows)
    return [scope, kind, len(rows), sum(r[-1]=='정상' for r in rows),
            sum(r[-1]=='차이' for r in rows),
            sum(r[0] in ('홈택스만','학사만') for r in rows),
            needs_review, '확인필요' if needs_review else '정상']


def apply_sample_style(ws, sample):
    columns = {c.value: c.column for c in sample[1]}
    for attr in ('sheet_format','page_margins','page_setup','print_options','sheet_properties'):
        setattr(ws, attr, copy(getattr(sample, attr)))
    ws.freeze_panes = sample.freeze_panes
    ws.row_dimensions[1].height = sample.row_dimensions[1].height
    ws.sheet_view.showGridLines = sample.sheet_view.showGridLines
    ws.sheet_view.zoomScale = sample.sheet_view.zoomScale
    for col in ws.columns:
        source_col = columns[col[0].value]
        ws.column_dimensions[col[0].column_letter].width = sample.column_dimensions[get_column_letter(source_col)].width
        for cell in col:
            source = sample.cell(1 if cell.row == 1 else 2, source_col)
            for attr in ('font','fill','border','alignment','protection','number_format'):
                setattr(cell, attr, copy(getattr(source, attr)))

    for column, pixels in [('A', 76), ('C', 240), ('H', 240)]:
        ws.column_dimensions[column].width = (pixels - 5) / 7


def format_report(wb):
    template = load_workbook(Path(__file__).parent / 'templates' / 'result_style.xlsx')
    for ws in wb:
        ws.auto_filter.ref = ws.dimensions
        if ws.freeze_panes is None:
            ws.freeze_panes = 'C2'
        ws.row_dimensions[1].height = 28
        for cell in ws[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24476B')
            cell.alignment = Alignment(vertical='center')
        for col in ws.columns:
            width = max(sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in str(cell.value or '')) for cell in col)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(60, max(18, width + 4))
            for cell in col[1:]:
                if isinstance(cell.value, (int, float, Decimal)):
                    value = Decimal(str(cell.value))
                    if value == value.to_integral_value():
                        cell.number_format = '#,##0;[Red]-#,##0;0'
                    else:
                        places = max(1, -value.normalize().as_tuple().exponent)
                        pattern = '#,##0.' + '0' * places
                        cell.number_format = f'{pattern};[Red]-{pattern};0'
                else:
                    cell.alignment = Alignment(wrap_text=True, vertical='center')
        headers = [cell.value for cell in ws[1]]
        if '금액검증' in headers and all(h in [c.value for c in template.active[1]] for h in headers):
            apply_sample_style(ws, template.active)
        if any(kind in ws.title for kind in ('매입세금계산서','매출세금계산서')) and len(headers)==15 and '금액검증' in headers:
            for index,width in enumerate(TAX_INVOICE_WIDTHS,1):
                ws.column_dimensions[get_column_letter(index)].width=width
        if '금액검증' in headers or '검증결과' in headers:ws.column_dimensions['A'].width=(90-5)/7
        if '금액검증' in headers:
            verdict_col = headers.index('금액검증')
            for row in ws.iter_rows(min_row=2):
                if row[verdict_col].value == '차이':
                    for cell in row:
                        cell.fill = PatternFill('solid', fgColor='FFFF00')
        elif '검증결과' in headers:
            for row in ws.iter_rows(min_row=2):
                if row[headers.index('검증결과')].value == '확인필요':
                    for cell in row:
                        cell.fill = PatternFill('solid', fgColor='FFFF00')
    template.close()


def excel_rows(path, start):
    """첫 시트의 행을 읽고 파일 핸들을 항상 닫는다."""
    if path.suffix.lower() == '.xls':
        try:
            wb = open_legacy_workbook(path)
        except xlrd.XLRDError as e:
            raise ValueError(f'{path.name}: XLS 파일을 읽을 수 없습니다. 암호 또는 실제 파일 형식을 확인하세요. ({e})') from e
        try:
            ws = wb.sheet_by_index(0)
            if ws.nrows < start:
                raise ValueError(f'{path.name}: 데이터 시작 행({start})이 없습니다.')
            for r in range(start - 1, ws.nrows):
                values = []
                for cell in ws.row(r):
                    if cell.ctype == xlrd.XL_CELL_ERROR:
                        raise ValueError(f'{path.name}: {r + 1}행에 Excel 오류 셀이 있습니다.')
                    value = cell.value
                    # XLS 숫자는 실수로 반환된다. 식별번호에 '.0'이 붙지 않게 한다.
                    if cell.ctype == xlrd.XL_CELL_NUMBER and value.is_integer():
                        value = int(value)
                    values.append(value)
                yield values
        finally:
            wb.release_resources()
    else:
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.worksheets[0]
            if ws.max_row < start:
                raise ValueError(f'{path.name}: 데이터 시작 행({start})이 없습니다.')
            yield from ws.iter_rows(min_row=start, values_only=True)
        finally:
            wb.close()


def read(path, home, tax, result):
    path = Path(path)
    rows = excel_rows(path, 10 if home else 2)
    count = 0
    try:
        for row in rows:
            row = list(row) + [None] * 8
            raw, name = (row[1], row[2]) if home else (row[0], row[1])
            k = key(raw)
            if not k: continue
            indexes = ([4,5,6] if tax else [4]) if home else ([5,6,7] if tax else [7])
            amounts = [number(row[i]) for i in indexes]
            if k not in result: result[k] = [str(raw), str(name or ''), [Decimal(0)] * len(indexes)]
            result[k][2] = [a+b for a,b in zip(result[k][2], amounts)]
            count += 1
        if not count: raise ValueError(f'{path.name}: 유효한 거래처 행이 없습니다. 빈 자료인지 형식을 확인하세요.')
    finally:
        rows.close()

def compare(ht, sc):
    used = set(); rows = []
    for k, h in ht.items():
        candidates = [k] if k in sc else [s for s in sc if s[2:8] == k[2:8] and (k.startswith('P:') or s.startswith('P:'))]
        match = candidates[0] if len(candidates) == 1 else None
        status = ('일치(마스킹)' if k.startswith('P:') or (match and match != k) else '일치') if match else ('확인필요(복수 후보)' if candidates else '홈택스만')
        s = sc.get(match)
        if match: used.add(match)
        rows.append(make_row(status, h, s))
    rows.extend(make_row('학사만', None, s) for k,s in sc.items() if k not in used)
    return rows

def make_row(status, h, s):
    n = len((h or s)[2]); zeros = [Decimal(0)] * n
    a = h[2] if h else zeros; b = s[2] if s else zeros
    differences = [x-y for x,y in zip(a,b)]
    normal = bool(h and s and not any(differences)) or bool(h and not s and not any(a))
    verdict = '확인필요' if status.startswith('확인필요') else ('정상' if normal else '차이')
    return [status, h[0] if h else '', h[1] if h else '', *a, s[0] if s else '', s[1] if s else '', *b, *differences, verdict]

def discover(root, months):
    found = {}; problems = []
    for month in months:
        folder = Path(root) / f'{month}월'
        if not folder.is_dir(): problems.append(f'폴더 없음: {folder}'); continue
        groups = {(kind,home): [] for kind in KINDS for home in (True,False)}
        for p in sorted(folder.iterdir()):
            if not p.is_file() or p.name.startswith('~$'): continue
            if p.suffix.lower() not in ('.xlsx','.xlsm','.xls','.xlsb'): continue
            if p.suffix.lower() == '.xlsb':
                problems.append(f'{p.name}: Excel에서 .xlsx로 저장해 주세요.'); continue
            n = p.stem
            source = [s for s in ('홈택스','학사') if s in n]
            sides = [s for s in ('매입','매출') if s in n]
            if len(source)!=1 or len(sides)!=1 or '계산서' not in n:
                problems.append(f'분류 불가: {p.name} (홈택스/학사, 매입/매출, 세금계산서/계산서 필요)'); continue
            kind = sides[0] + ('세금계산서' if '세금계산서' in n else '계산서')
            groups[kind, source[0]=='홈택스'].append(p)
        for (kind,home), files in groups.items():
            if len(files)!=1: problems.append(f'{month}월 {"홈택스" if home else "학사"} {kind}: 파일 {len(files)}개 (정확히 1개 필요)')
        found[month] = groups
    if problems: raise ValueError('\n'.join(problems))
    return found

def run(root, months, label, save=True):
    months = tuple(months)
    if not months or len(set(months)) != len(months) or any(m not in range(1,13) for m in months): raise ValueError('월 선택이 올바르지 않습니다.')
    files = discover(root, months)
    wb = Workbook(); summary = wb.active; summary.title='검증요약'
    summary.append(['범위','구분','전체','정상','차이','한쪽만 존재','확인필요 건수','검증결과'])
    scopes = [(f'{m:02}월',(m,)) for m in months]
    if len(months)>1: scopes.append(('기간누적', months))
    for scope, selected in scopes:
        for kind in KINDS:
            ht, sc = {}, {}; tax = '세금' in kind
            for m in selected:
                read(files[m][kind,True][0],True,tax,ht)
                read(files[m][kind,False][0],False,tax,sc)
            rows=compare(ht,sc); ws=wb.create_sheet(scope+'_'+kind)
            fields=['공급가액','세액','합계금액'] if tax else ['공급가액']
            ws.append(['상태','사업자번호HT','상호_HT',*[x+'_HT' for x in fields],'사업자번호HK','거래처명',*[x+'_HK' for x in fields],*[x+'차이' for x in fields],'금액검증'])
            for row in rows:
                ws.append(row)
                for cell in ws[ws.max_row]:
                    if isinstance(cell.value,str): cell.data_type='s'
            ws.freeze_panes='D2'; ws.auto_filter.ref=ws.dimensions
            summary.append(summary_row(scope,kind,rows))
    format_report(wb)
    if not save:return wb
    target=result_path('세금계산서 검증')
    wb.save(target); wb.close()
    return target


def year_folder(root, year):
    year = str(year).strip()
    if not re.fullmatch(r"[0-9]{4}", year) or not 1900 <= int(year) <= 9999:
        raise ValueError('연도를 1900~9999 사이의 네 자리 숫자로 입력하세요.')
    if not str(root).strip():
        raise ValueError('taxinvoice 기본 폴더를 선택하세요.')
    return Path(root) / year


def create_year_folders(root, year):
    folder = year_folder(root, year)
    for month in range(1, 13):
        (folder / f'{month}월').mkdir(parents=True, exist_ok=True)
    return folder
