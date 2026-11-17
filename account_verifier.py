"""CMS·학사 예금시재 비교: 첨부 CashAccountBalanceVerifier VBA 규칙."""
from result_paths import result_path
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from verifier import excel_rows


def yesterday():
    return (date.today() - timedelta(days=1)).isoformat()


def dated_folder(root, day):
    if not str(root).strip():
        raise ValueError('account verification 기본 폴더를 선택하세요.')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('날짜를 YYYY-MM-DD 형식으로 입력하세요.')
    try:
        date.fromisoformat(day)
    except ValueError as e:
        raise ValueError('존재하지 않는 날짜입니다.') from e
    return Path(root) / day


def create_input_folder(root, day):
    folder = dated_folder(root, day)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def account_key(value):
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, (int, float, Decimal)):
        value = format(Decimal(str(value)), 'f')
        if '.' in value:
            value = value.rstrip('0').rstrip('.')
    return ''.join(re.findall(r'[0-9]', str(value)))


def amount(value):
    """VBA의 금액변환: 빈 값/비숫자는 None, 괄호는 음수."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    negative = text.startswith('(') and text.endswith(')')
    text = text.replace(',', '').replace(' ', '').replace('(', '').replace(')', '')
    try:
        result = Decimal(text)
        if not result.is_finite():
            return None
        return -result if negative else result
    except InvalidOperation:
        return None


def read_accounts(path, cms):
    path = Path(path)
    if path.suffix.lower() not in ('.xls', '.xlsx', '.xlsm'):
        raise ValueError(f'{path.name}: .xls, .xlsx, .xlsm 파일을 선택하세요.')
    values = {}; warnings = []
    rows = excel_rows(path, 1)
    try:
        for index, row in enumerate(rows, 1):
            row = list(row) + [None] * 11
            key = account_key(row[3] if cms else row[2])
            if not key:
                continue
            if cms:
                balances = [amount(row[i]) for i in range(7,11)]
                if all(v is not None and v == 0 for v in balances):
                    continue
                balance = balances[-1]
                if balance is None:
                    warnings.append([path.name, index, 'CMS 잔액을 읽을 수 없어 행 제외'])
                    continue
            else:
                parts = [amount(row[i]) for i in (3,4,5)]
                if any(v is None for v in parts):
                    warnings.append([path.name, index, '학사 D/E/F 빈값·비숫자를 0으로 계산'])
                d,e,f = [v if v is not None else Decimal(0) for v in parts]
                balance = d + e - f
            values[key] = values.get(key, Decimal(0)) + balance
    finally:
        rows.close()
    return values, warnings


def compare_accounts(cms, school):
    rows = []
    for key in sorted(cms.keys() | school.keys()):
        c, s = cms.get(key), school.get(key)
        diff = None; status = '불일치'
        if c is None:
            note = 'CMS 계좌현황에 없음'
        elif s is None:
            note = '학사 계좌현황에 없음'
        else:
            diff = c - s
            status = '일치' if diff == 0 else '불일치'
            note = '' if diff == 0 else '잔액 차이'
        rows.append([key,c,s,diff,status,note])
    return rows


def find_inputs(folder):
    if not folder.is_dir():
        raise ValueError(f'검증 폴더가 없습니다: {folder}')
    files = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith('~$') and p.suffix.lower() in ('.xls','.xlsx','.xlsm','.xlsb')]
    cms = [p for p in files if 'cms' in p.stem.lower() and '학사' not in p.stem]
    school = [p for p in files if '학사' in p.stem and 'cms' not in p.stem.lower()]
    if len(cms) != 1 or len(school) != 1:
        details = []
        for label, candidates in [('CMS', cms), ('학사', school)]:
            names = ', '.join(p.name for p in candidates) if candidates else '없음'
            details.append(f'{label}: {len(candidates)}개 ({names})')
        raise ValueError(f'검색 폴더: {folder}\n' + '\n'.join(details) + '\n\nCMS와 학사 파일이 각각 1개 필요합니다. 다른 위치에 있다면 직접 선택하세요.')
    return cms[0], school[0]


def style_account_report(wb):
    for ws in wb:
        ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
        ws.row_dimensions[1].height = 28
        for cell in ws[1]:
            cell.font = Font(name='맑은 고딕', size=11, bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24476B')
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.font = Font(name='맑은 고딕', size=11)
                cell.alignment = Alignment(vertical='center', wrap_text=True)
                if isinstance(cell.value,(int,float,Decimal)):
                    value = Decimal(str(cell.value))
                    places = max(0,-value.normalize().as_tuple().exponent)
                    pattern = '#,##0' + ('.'+'0'*places if places else '')
                    cell.number_format = f'{pattern};[Red]-{pattern};0'
            if ws.title == '검증결과' and row[4].value == '불일치':
                for cell in row: cell.fill = PatternFill('solid', fgColor='FFFF00')
        widths = [22,22,22,22,14,30] if ws.title == '검증결과' else [34,28,60]
        for i,width in enumerate(widths,1):
            ws.column_dimensions[chr(64+i)].width = width
    for cell in wb['검증결과']['A'][1:]:
        cell.number_format = '@'


def run_account(root, day, cms_path=None, school_path=None, save=True):
    if bool(cms_path) != bool(school_path):
        raise ValueError('CMS 파일과 학사 파일을 모두 선택하세요.')
    cms_path, school_path = (Path(cms_path),Path(school_path)) if cms_path and school_path else find_inputs(dated_folder(root,day))
    if cms_path.resolve() == school_path.resolve():
        raise ValueError('CMS와 학사 자료에 서로 다른 파일을 선택하세요.')
    cms, cw = read_accounts(cms_path,True)
    school, sw = read_accounts(school_path,False)
    rows = compare_accounts(cms,school)
    if not rows:
        raise ValueError('비교 가능한 계좌번호/잔액 데이터를 찾지 못했습니다.')
    wb = Workbook(); summary = wb.active; summary.title='검증요약'
    summary.append(['항목','값'])
    matched = sum(r[4]=='일치' for r in rows)
    ct, st = sum(cms.values(),Decimal(0)), sum(school.values(),Decimal(0))
    for item in [('검증일자',day),('전체 계좌',len(rows)),('일치',matched),('불일치',len(rows)-matched),('CMS만 존재',len(cms.keys()-school.keys())),('학사만 존재',len(school.keys()-cms.keys())),('CMS 총 잔액',ct),('학사 총 잔액',st),('총 잔액 차이',ct-st),('자료 확인 건수',len(cw)+len(sw)),('검증결과','확인필요' if matched!=len(rows) or cw or sw else '정상')]:
        summary.append(item)
    ws = wb.create_sheet('검증결과')
    ws.append(['계좌번호','CMS 현재 잔액','학사 현재 잔액','차이','일치 여부','비고'])
    for row in rows: ws.append(row)
    if cw or sw:
        notes=wb.create_sheet('자료확인');notes.append(['파일','행','안내'])
        for warning in cw+sw: notes.append(warning)
    # 파일명 등 외부 텍스트가 수식으로 해석되지 않게 한다.
    for sheet in wb:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value,str): cell.data_type='s'
    style_account_report(wb)
    if not save:return wb
    target=result_path('예금시재 검증')
    wb.save(target);wb.close()
    return target
