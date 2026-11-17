"""원장 조회·Excel 통합. 원본은 읽기만 하며 문자열 수식은 실행하지 않는다."""
from collections import defaultdict
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from functools import lru_cache
import re
import tempfile
import os
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from verifier import open_legacy_workbook

LEDGER_COLUMNS = '년도 회계단위 관 항 목 회계일자 전표번호 대사업 중사업 소사업 세부사업 부서명 차변 대변 거래선명 적요 재원'.split()


BUSINESS_COLUMNS = ['대사업','중사업','소사업']
LEDGER_DISPLAY_COLUMNS = [c for c in LEDGER_COLUMNS if c not in BUSINESS_COLUMNS]


def discover_ledger_years(folder):
    folder=Path(folder)
    if not folder.exists():return {}
    if not folder.is_dir():raise ValueError('lodges는 폴더여야 합니다.')
    result={}
    candidates=list(folder.iterdir())
    for child in list(candidates):
        if child.is_dir() and re.fullmatch(r'20\d{2}',child.name):
            candidates.extend(child.iterdir())
    for path in sorted(candidates):
        if not path.is_file() or path.name.startswith('~$') or path.suffix.lower() not in ('.xls','.xlsx','.xlsm'):continue
        years=re.findall(r'(?<!\d)(20\d{2})(?!\d)',path.stem)
        folder_year=path.parent.name if path.parent!=folder and re.fullmatch(r'20\d{2}',path.parent.name) else None
        if folder_year:years.append(folder_year)
        years=set(years)
        if not years:continue
        if len(years)>1:raise ValueError(f'{path.name}: 파일명/폴더명의 원장 연도가 서로 다릅니다.')
        year=years.pop()
        if year in result:raise ValueError(f'{year}년 원장 파일이 중복됩니다. 원장통합으로 하나로 합친 뒤 원본은 다른 폴더로 옮겨 주세요.')
        result[year]=path
    return dict(sorted(result.items(),reverse=True))


def ledger_totals(records):
    return {c:sum((r[c] for r in records),Decimal(0)) for c in ('차변','대변')}


def ledger_total_row(records,columns):
    totals=ledger_totals(records)
    return ['조회 전체 합계' if i==0 else totals.get(c,'') for i,c in enumerate(columns)]


def rows(path):
    path = Path(path)
    if path.suffix.lower() == '.xls':
        import xlrd
        wb = open_legacy_workbook(path)
        try:
            sheet = wb.sheet_by_index(0)
            for ri in range(sheet.nrows):
                row = []
                for cell in sheet.row(ri):
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_ERROR:
                        raise ValueError(f'{path.name}: {ri+1}행에 Excel 오류 값이 있습니다.')
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        value = xlrd.xldate_as_datetime(value, wb.datemode)
                    elif isinstance(value, float) and value.is_integer():
                        value = int(value)
                    row.append(value)
                yield row
        finally:
            wb.release_resources()
    elif path.suffix.lower() in ('.xlsx', '.xlsm'):
        from fast_excel import validated_rows
        yield from validated_rows(path)
    else:
        raise ValueError(f'{path.name}: .xls / .xlsx / .xlsm 파일을 선택하세요.')


def text(value):
    if value is None:return ''
    if isinstance(value, float) and value.is_integer():return str(int(value))
    return str(value).strip()


def money(value):
    raw = text(value).replace(',', '').replace(' ', '')
    if not raw or raw == '-':return Decimal(0)
    if raw.startswith('(') and raw.endswith(')'):raw = '-'+raw[1:-1]
    try:
        result = Decimal(raw)
        if not result.is_finite():raise InvalidOperation
        return result
    except InvalidOperation:
        raise ValueError(f'금액으로 읽을 수 없는 값: {value}')


def date_text(value):
    if isinstance(value, (datetime, date)):return value.strftime('%Y-%m-%d')
    return _date_string(text(value))


@lru_cache(maxsize=4096)
def _date_string(raw):
    if not raw:return ''
    digits = re.sub(r'[^0-9]', '', raw)
    if len(digits) == 8:
        try:return datetime.strptime(digits, '%Y%m%d').strftime('%Y-%m-%d')
        except ValueError:pass
    raise ValueError(f'회계일자를 읽을 수 없습니다: {raw}')


def load_ledger(path,with_provenance=False):
    from ledger_cache import load
    return load(path,LEDGER_COLUMNS,_read_ledger,with_provenance)


def _read_ledger(path,with_provenance=False):
    source_path=str(Path(path).resolve())
    stream = rows(path)
    try:
        header = [text(c) for c in next(stream, [])]
        missing = [c for c in LEDGER_COLUMNS if c not in header]
        if missing:raise ValueError('원장 첫 행에 필요한 열이 없습니다: '+', '.join(missing))
        if any(header.count(c) != 1 for c in LEDGER_COLUMNS):raise ValueError('원장 열 제목이 중복됩니다.')
        indices = [header.index(c) for c in LEDGER_COLUMNS]
        records = []
        for number, row in enumerate(stream, 2):
            if not any(text(v) for v in row):continue
            record = {c:row[i] if i < len(row) else None for c,i in zip(LEDGER_COLUMNS, indices)}
            try:
                for c in LEDGER_COLUMNS:
                    record[c] = money(record[c]) if c in ('차변','대변') else date_text(record[c]) if c == '회계일자' else text(record[c])
            except ValueError as e:raise ValueError(f'{Path(path).name} {number}행: {e}') from e
            if with_provenance:record.update(_source_file=source_path,_source_row=number)
            records.append(record)
        return records
    finally:stream.close()


def filter_ledger(records, filters=None, start='', end='', query=''):
    filters = filters or {}
    start = date_text(start);end = date_text(end)
    if start and end and start > end:raise ValueError('시작일이 종료일보다 늦습니다.')
    query = query.strip().casefold()
    return [r for r in records if all(not v or r[k] == v for k,v in filters.items())
            and (not start or r['회계일자'] >= start) and (not end or bool(r['회계일자']) and r['회계일자'] <= end)
            and (not query or any(query in r[c].casefold() for c in ('전표번호','거래선명','적요','부서명','재원','대사업','중사업','소사업','세부사업')))]


def ledger_summary(records, level='목'):
    keys = ['년도','회계단위'] + ['관','항','목'][:['관','항','목'].index(level)+1]
    totals = defaultdict(lambda:[0,Decimal(0),Decimal(0)])
    for r in records:
        item = totals[tuple(r[k] for k in keys)]
        item[0] += 1;item[1] += r['차변'];item[2] += r['대변']
    return keys+['건수','차변','대변','차변-대변'], [list(k)+v+[v[1]-v[2]] for k,v in sorted(totals.items())]


# XLS는 XLSX(XML 1.0)에 저장할 수 없는 제어문자를 포함할 수 있다.
# 정상적인 줄바꿈(CR/LF)·탭·한글·이모지는 그대로 보존한다.
_INVALID_XML_TEXT = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]')


def excel_safe_text(value):
    return _INVALID_XML_TEXT.sub('',value) if isinstance(value,str) else value


def append_row(sheet, values):
    values=[excel_safe_text(value) for value in values]
    sheet.append(values)
    for index in range(1,len(values)+1):
        c=sheet.cell(sheet._current_row,index)
        if isinstance(c.value,str):c.data_type='s'
        elif isinstance(c.value,(int,float,Decimal)):
            c.number_format='#,##0.##########' if c.value != int(c.value) else '#,##0'
            c.alignment=Alignment(horizontal='right')
        elif isinstance(c.value,(date,datetime)):c.number_format='yyyy-mm-dd'


def format_sheet(sheet,all_rows=False):
    sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
    for c in sheet[1]:c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='244C70')
    for i in range(1,sheet.max_column+1):
        width=max((sum(2 if ord(ch)>127 else 1 for ch in text(row[i-1].value)) for row in sheet.iter_rows(max_row=sheet.max_row if all_rows else min(sheet.max_row,300))),default=10)
        sheet.column_dimensions[get_column_letter(i)].width=min(65,max(14,width+2))
    sheet.sheet_properties.pageSetUpPr.fitToPage=True
    sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0;sheet.print_title_rows='1:1'


def save_atomic(wb, target):
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(suffix='.xlsx',dir=target.parent);os.close(fd)
    try:wb.save(tmp);os.replace(tmp,target)
    finally:
        wb.close()
        if os.path.exists(tmp):os.unlink(tmp)
    return target


def export_ledger(records,target,level='목',include_summary=True):
    wb=Workbook()
    if include_summary:
        summary=wb.active;summary.title='과목별 집계'
        header,data=ledger_summary(records,level);append_row(summary,header)
        for row in data:append_row(summary,row)
        detail=wb.create_sheet('거래 내역')
    else:detail=wb.active;detail.title='거래 내역'
    append_row(detail,LEDGER_COLUMNS)
    for record in records:append_row(detail,[record[c] for c in LEDGER_COLUMNS])
    append_row(detail,ledger_total_row(records,LEDGER_COLUMNS))
    for c in detail[detail.max_row]:
        c.font=Font(bold=True,color='FFFFFF');c.fill=PatternFill('solid',fgColor='244C70')
    for sheet in wb:format_sheet(sheet,all_rows=True)
    detail.auto_filter.ref=f'A1:{get_column_letter(len(LEDGER_COLUMNS))}{len(records)+1}'
    return save_atomic(wb,target)


def merge_excel(sources,target,ledger=False):
    sources=[Path(p) for p in sources];target=Path(target)
    if not sources:raise ValueError('통합할 파일을 선택하세요.')
    if len({p.resolve() for p in sources}) != len(sources):raise ValueError('같은 파일이 중복 선택되었습니다.')
    if target.resolve() in {p.resolve() for p in sources}:raise ValueError('결과 파일은 원본과 다른 이름으로 저장하세요.')
    wb=Workbook();wb.remove(wb.active);headers=None;count=0
    # 기존 재무제표 통합기의 단위 → 구분 순서를 유지한다.
    def order(p):
        name=re.sub(r'\s+','',p.stem)
        return (next((i for i,s in enumerate(('(전체)','(등록금)','(비등록금)')) if s in name),3),
                next((i for i,s in enumerate(('자금계산서','재무상태표','운영계산서','합계잔액시산표')) if s in name),4),name)
    if not ledger:sources=sorted(sources,key=order)
    try:
        for path in sources:
            stream=rows(path)
            try:
                header=next(stream,[])
                while header and not text(header[-1]):header.pop()
                if not header or not any(text(v) for v in header):raise ValueError(f'{path.name}: 첫 행의 헤더가 없습니다.')
                if ledger:
                    normalized=[text(v) for v in header]
                    if headers is None:
                        headers=normalized;sheet=wb.create_sheet('원장통합');append_row(sheet,header)
                    elif normalized!=headers:raise ValueError(f'{path.name}: 헤더의 이름 또는 순서가 첫 파일과 다릅니다. 통합을 중단했습니다.')
                else:
                    name=re.sub(r'[\\/*?:\[\]]','_',path.stem).strip("'")[:31] or 'Sheet'
                    sheet=wb.create_sheet(name);append_row(sheet,header)
                for number,row in enumerate(stream,2):
                    if not any(text(v) for v in row):continue
                    if any(text(v) for v in row[len(header):]):raise ValueError(f'{path.name} {number}행: 헤더 밖에 데이터가 있습니다.')
                    if sheet._current_row>=1048576:raise ValueError('Excel 한 시트의 최대 행 수를 초과합니다. 파일을 나눠 통합하세요.')
                    append_row(sheet,row[:len(header)]);count+=1
            finally:stream.close()
        for sheet in wb:format_sheet(sheet)
        save_atomic(wb,target)
    finally:wb.close()
    return target,count
