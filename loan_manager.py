"""LoanStatusMacros의 원자료 집계 규칙을 사용하는 차입금 관리."""
from result_paths import result_path
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from shutil import copyfile, copyfileobj
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZipFile
from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import from_excel, WINDOWS_EPOCH, MAC_EPOCH
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from verifier import open_legacy_workbook
from loan_report_style import apply_loan_sample

ZERO=Decimal(0)
HEADERS=['예정 원금','예정 총이자','총원리금','납부원금','납부 총이자','총 납부 원리금','상태']
LOAN_EXCEL_SUFFIXES=('.xlsx','.xls','.xlsm')


def target_year(value):
    if not re.fullmatch(r'[0-9]{4}',str(value)) or not 1900<=int(value)<=9999:
        raise ValueError('조회 연도를 네 자리 숫자로 입력하세요.')
    return int(value)


def find_loan_files(root):
    if not str(root).strip():raise ValueError('차입금 원자료 폴더를 선택하세요.')
    root=Path(root)
    if not root.is_dir():raise ValueError(f'원자료 폴더가 없습니다: {root}')
    unsupported=[p.name for p in root.iterdir() if p.is_file() and p.suffix.lower()=='.xlsb' and not p.name.startswith('~$')]
    if unsupported:raise ValueError('.xlsb 파일은 .xlsx로 저장해 주세요: '+', '.join(unsupported))
    files=sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() in LOAN_EXCEL_SUFFIXES and not p.name.startswith('~$'))
    if not files:raise ValueError(f'차입금 원자료 Excel 파일이 없습니다: {root}')
    return files


def numeric(value):
    if value is None or isinstance(value,bool):return ZERO
    try:
        n=Decimal(str(value).replace(',','').strip())
        return n if n.is_finite() else ZERO
    except InvalidOperation:return ZERO


def parse_date(value, epoch=WINDOWS_EPOCH):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    if value is None or isinstance(value,bool):return None
    text=str(value).strip()
    # Eight-digit dates are parsed before Excel date serials.
    digits=''.join(re.findall(r'[0-9]',text))
    if len(digits)==8:
        try:return date(int(digits[:4]),int(digits[4:6]),int(digits[6:]))
        except ValueError:return None
    try:
        serial=float(text)
        if 20000<=serial<=90000:
            return from_excel(round(serial),epoch).date()
    except (ValueError,TypeError,OverflowError):pass
    try:return datetime.fromisoformat(text).date()
    except ValueError:return None


def read_rows(path):
    """계산된 셀 값과 파일의 날짜 체계를 읽고 원본은 수정하지 않는다."""
    if path.suffix.lower()=='.xls':
        import xlrd
        w=open_legacy_workbook(path)
        try:
            s=w.sheet_by_index(0);data=[]
            for r in range(s.nrows):
                row=[]
                for c in range(min(s.ncols,22)):
                    cell=s.cell(r,c)
                    if cell.ctype==xlrd.XL_CELL_ERROR:raise ValueError(f'{path.name}: {r+1}행에 Excel 오류 셀이 있습니다.')
                    row.append(cell.value)
                data.append(row+[None]*(22-len(row)))
            return data, MAC_EPOCH if w.datemode else WINDOWS_EPOCH
        finally:w.release_resources()
    w=load_workbook(path,read_only=True,data_only=True)
    formulas=load_workbook(path,read_only=True,data_only=False)
    try:
        s=w.worksheets[0];f=formulas.worksheets[0];data=[]
        for r,(cells,original) in enumerate(zip(s.iter_rows(max_col=22),f.iter_rows(max_col=22)),1):
            for c in (1,2,5,10,15,16,21):
                if cells[c].data_type=='e':raise ValueError(f'{path.name}: {r}행에 Excel 오류 셀이 있습니다.')
                if original[c].data_type=='f' and cells[c].value is None:
                    raise ValueError(f'{path.name}: {r}행의 수식 계산값이 없습니다. Excel에서 열어 계산 후 저장해 주세요.')
            data.append([cell.value for cell in cells])
        return data,w.epoch
    finally:w.close();formulas.close()


def analyze(path,scheduled,paid,warnings):
    rows,epoch=read_rows(path)
    last=lambda col:next((numeric(row[col]) for row in reversed(rows) if numeric(row[col])!=0),ZERO)
    totalp=last(2)+last(15);totali=last(5)+last(16)
    pp=ZERO;pi=ZERO;count=0;years=[];valid_dates=0
    for index,row in enumerate(rows,1):
        due=parse_date(row[1],epoch);actual=parse_date(row[10],epoch)
        if due:years.append(due.year)
        if due or actual:
            valid_dates+=1
            for c in (2,5,15,16):
                value=row[c]
                if value is not None and str(value).strip():
                    try:
                        n=Decimal(str(value).replace(',','').strip())
                        if not n.is_finite():raise InvalidOperation
                    except InvalidOperation:warnings.append([path.name,index,get_column_letter(c+1),'비숫자 금액을 0으로 집계'])
            for c,label,parsed in ((1,'예정일',due),(10,'납부일',actual)):
                if row[c] is not None and str(row[c]).strip() and parsed is None:warnings.append([path.name,index,label,'날짜를 해석하지 못했습니다.'])
        principal=numeric(row[2]);interest=numeric(row[5])+numeric(row[16])
        if due and (principal or interest):
            key=(due.year,(due.month-1)//3+1)
            scheduled[key][0]+=principal;scheduled[key][1]+=interest
        if actual:
            principal+=numeric(row[15])
            if principal or interest:
                pp+=principal;pi+=interest;count+=1
                basis=due or actual;key=(basis.year,(basis.month-1)//3+1)
                paid[key][0]+=principal;paid[key][1]+=interest
    if not valid_dates:raise ValueError(f'{path.name}: 첫 시트 B열 예정일 또는 K열 납부일을 찾지 못했습니다. 집계 결과 파일이 아닌 원자료인지 확인하세요.')
    if pp>totalp or pi>totali:warnings.append([path.name,'','합계','상환액이 총액보다 큽니다. 원자료 하단 합계와 중복 자료를 확인하세요.'])
    return [path.stem,min(years) if years else None,max(years) if years else None,totalp,pp,max(totalp-pp,ZERO),totali,pi,max(totali-pi,ZERO),count]


def status_row(label,s,p):
    sp,si=s;pp,pi=p
    return [label,sp,si,sp+si,pp,pi,pp+pi,'완료' if pp+pi>=sp+si else '미완료']


def sum_pair(values):
    return [sum((v[i] for v in values),ZERO) for i in (0,1)]


def style(wb):
    for ws in wb:
        ws.freeze_panes='B2';ws.auto_filter.ref=ws.dimensions;ws.row_dimensions[1].height=30
        for cell in ws[1]:
            if cell.value is not None:
                cell.font=Font(name='맑은 고딕',size=11,bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='24476B')
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment=Alignment(vertical='center',wrap_text=True)
                if isinstance(cell.value,(int,float,Decimal)):
                    n=Decimal(str(cell.value));places=max(0,-n.normalize().as_tuple().exponent)
                    fmt='#,##0'+('.'+'0'*places if places else '')
                    cell.number_format=f'{fmt};[Red]-{fmt};0'
                if cell.value=='미완료':
                    cell.fill=PatternFill('solid',fgColor='FFFF00')
            if row[0].value=='합계':
                for cell in row:cell.font=Font(bold=True);cell.fill=PatternFill('solid',fgColor='DDEBF7')
        for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=22
        ws.column_dimensions['A'].width=48 if ws.title=='파일별현황' else 25
        ws.sheet_properties.pageSetUpPr.fitToPage=True;ws.page_setup.orientation='landscape';ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    wb['요약'].column_dimensions['B'].width=48
    wb['요약'].auto_filter.ref=None
    for row in wb['파일별현황'].iter_rows(min_row=2):
        for c in (1,2):row[c].number_format='0'
    for ws in wb:
        for row in ws:
            for cell in row:
                if isinstance(cell.value,str):cell.data_type='s'


def build_loan_report(root,year,*,source_label=None):
    year=target_year(year);files=find_loan_files(root)
    scheduled=defaultdict(lambda:[ZERO,ZERO]);paid=defaultdict(lambda:[ZERO,ZERO]);warnings=[]
    infos=[analyze(p,scheduled,paid,warnings) for p in files]
    report_years={y for y,q in scheduled.keys()|paid.keys()}|{y for info in infos for y in info[1:3] if y}
    wb=Workbook();summary=wb.active;summary.title='요약'
    summary.append(['항목','금액',None,'분기',*HEADERS])
    totalp=sum((r[3] for r in infos),ZERO);pp=sum((r[4] for r in infos),ZERO)
    totali=sum((r[6] for r in infos),ZERO);pi=sum((r[7] for r in infos),ZERO)
    source=('자료 출처',source_label) if source_label else ('원본 폴더',str(Path(root).resolve()))
    for label,value in [source,('파일 수',len(files)),('총 원금',totalp),('상환 원금',pp),('남은 원금',max(totalp-pp,ZERO)),('총 이자',totali),('상환 이자',pi),('남은 이자',max(totali-pi,ZERO)),('조회 연도',year),('자료 확인 건수',len(warnings))]:summary.append([label,value])
    for q in range(1,5):
        values=status_row(f'{year}년 {q}분기',scheduled[year,q],paid[year,q])
        for c,v in enumerate(values,4):summary.cell(q+1,c,v)
    for c,v in enumerate(status_row('합계',sum_pair([scheduled[year,q] for q in range(1,5)]),sum_pair([paid[year,q] for q in range(1,5)])),4):summary.cell(6,c,v)
    ws=wb.create_sheet('파일별현황');ws.append(['차입금명','시작연도','예정종료연도','총원금','상환원금','남은원금','총이자','상환이자','남은이자','상환건수'])
    for info in infos:ws.append(info)
    # 실제 납부일만 있는 자료도 현황에서 빠지지 않게 포함한다.
    low,high=(min(report_years),max(report_years)) if report_years else (year,year)
    annual=wb.create_sheet('연도별현황');annual.append(['연도',*HEADERS])
    quarter=wb.create_sheet('분기별현황');quarter.append(['분기',*HEADERS])
    for y in range(low,high+1):
        annual.append(status_row(f'{y}년',sum_pair([scheduled[y,q] for q in range(1,5)]),sum_pair([paid[y,q] for q in range(1,5)])))
        for q in range(1,5):quarter.append(status_row(f'{y}년 {q}분기',scheduled[y,q],paid[y,q]))
    total=status_row('합계',sum_pair(list(scheduled.values())),sum_pair(list(paid.values())))
    annual.append(total);quarter.append(total)
    selected=wb.create_sheet(f'{year}년_분기별상환예정');selected.append(['차입금명','구분','1분기','2분기','3분기','4분기','전체 합계'])
    for field,label in ((0,'예정원금'),(1,'예정이자'),(2,'소계')):
        values=[scheduled[year,q][field] if field<2 else sum(scheduled[year,q]) for q in range(1,5)]
        selected.append(['전체 차입금',label,*values,sum(values)])
    if warnings:
        ws=wb.create_sheet('자료확인');ws.append(['파일','행','항목','안내'])
        for warning in warnings:ws.append(warning)
    ws=wb.create_sheet('집계기준');ws.append(['항목','기준'])
    for row in [('총 원금','C열 마지막 0이 아닌 숫자 + P열 마지막 0이 아닌 숫자'),('총 이자','F열 마지막 0이 아닌 숫자 + Q열 마지막 0이 아닌 숫자'),('예정액','B열 예정일 기준, 원금 C열 / 이자 F+Q열'),('납부액','K열 납부일이 있는 행, 원금 C+P열 / 이자 F+Q열'),('납부 귀속','예정일이 있으면 예정일, 없으면 실제 납부일 기준'),('상태','납부 총원리금 ≥ 예정 총원리금이면 완료 (매크로 기준)'),('금액 해석','비숫자는 0으로 처리. 자료확인 시트가 있으면 확인 필요'),('조회 연도','요약 분기와 선택연도 상환예정표에 적용. 전체 현황은 모든 연도 포함')]:ws.append(row)
    style(wb)
    apply_loan_sample(wb)
    return wb


def upload_loan_sources(paths, storage):
    """Validate a complete replacement batch before committing it as one file."""
    sources = [Path(path) for path in paths]
    if not sources:
        raise ValueError('차입금 원자료 파일을 하나 이상 선택하세요.')
    names = set()
    for source in sources:
        if source.suffix.lower() not in LOAN_EXCEL_SUFFIXES or source.name.startswith('~$') or '\\' in source.name:
            raise ValueError(f'지원하지 않는 차입금 원자료입니다: {source.name}')
        key = source.name.casefold()
        if key in names:
            raise ValueError(f'같은 이름의 파일이 여러 개 있습니다: {source.name}')
        names.add(key)

    storage = Path(storage)
    with TemporaryDirectory(prefix='loan-upload-') as folder:
        copies = []
        for source in sources:
            copy = Path(folder)/source.name
            copyfile(source, copy)
            analyze(copy, defaultdict(lambda: [ZERO, ZERO]), defaultdict(lambda: [ZERO, ZERO]), [])
            copies.append(copy)

        storage.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=storage.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
        try:
            with ZipFile(temporary, 'w') as archive:
                for copy in copies:
                    archive.write(copy, arcname=copy.name)
            temporary.replace(storage)
        finally:
            temporary.unlink(missing_ok=True)
    return len(sources)


@contextmanager
def uploaded_loan_sources(storage):
    if not Path(storage).is_file():
        raise ValueError('자료 업로드에서 차입금 원자료를 먼저 선택하세요.')
    with TemporaryDirectory(prefix='loan-report-') as folder:
        with ZipFile(storage) as archive:
            for member in archive.infolist():
                name = member.filename
                if Path(name).name != name or '\\' in name or Path(name).suffix.lower() not in LOAN_EXCEL_SUFFIXES:
                    raise ValueError('저장된 차입금 자료를 읽을 수 없습니다. 다시 업로드하세요.')
                with archive.open(member) as source, (Path(folder)/name).open('xb') as copy:
                    copyfileobj(source, copy)
        yield folder


def build_uploaded_loan_report(storage, year):
    with uploaded_loan_sources(storage) as folder:
        return build_loan_report(folder, year, source_label='최근 업로드 자료')


def save_loan_report(wb):
    target=result_path('차입금관리')
    with NamedTemporaryFile(dir=target.parent,suffix='.tmp',delete=False) as stream:
        temporary=Path(stream.name)
    try:
        wb.save(temporary)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def generate_loans(root,year):
    wb=build_loan_report(root,year)
    try:return save_loan_report(wb)
    finally:wb.close()
