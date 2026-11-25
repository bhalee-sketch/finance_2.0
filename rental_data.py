"""Rental register analysis. Workbook annual income is authoritative, not payment timing."""
import calendar
import re
import hashlib
from contextlib import contextmanager
from io import BytesIO
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from openpyxl import load_workbook, Workbook
from finance_data import money, append_row, format_sheet, save_atomic


def clean(value):
    return '' if value is None else str(value).strip()


def parse_date(value):
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    match=re.fullmatch(r'\s*(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})\s*[.일]?\s*',str(value or ''))
    try:return date(*map(int,match.groups())) if match else None
    except ValueError:return None


def optional_money(value):
    return None if value is None or clean(value)=='' else money(value)


def read_rentals(path):
    path=Path(path);source_bytes=path.read_bytes();revision=hashlib.sha256(source_bytes).hexdigest();book=load_workbook(BytesIO(source_bytes),data_only=True);records=[];issues=[]
    try:
        for sheet in book:
            if [sheet.cell(2,c).value for c in (6,9,13,14)]!=['업체명','임대기간','임대보증금','임대료']:continue
            group=path.stem.removeprefix('임대사항_')
            merged_numbers={}
            for area in sheet.merged_cells.ranges:
                if area.min_col==area.max_col==1:
                    for row in range(area.min_row,area.max_row+1):merged_numbers[row]=sheet.cell(area.min_row,1).value
            for rn in range(3,sheet.max_row+1):
                row=[sheet.cell(rn,c).value for c in range(1,18)]
                if not row[5]:continue  # totals and unfilled rows are not contracts
                notes=[]
                try:
                    raw_number=merged_numbers.get(rn,row[0])
                    number=int(raw_number) if raw_number is not None and float(raw_number).is_integer() else None
                    if number is None:notes.append('계약번호 없음')
                    period=re.split(r'\s*[~～]\s*',clean(row[8]))
                    start,end=(parse_date(v) for v in period) if len(period)==2 else (None,None)
                    if start is None or end is None or start>end:
                        start=end=None;notes.append('계약기간 확인 필요')
                    entered,exited=parse_date(row[9]),parse_date(row[11])
                    if row[9] and entered is None:notes.append('입주일 확인 필요')
                    if row[11] and exited is None:notes.append('퇴거일 확인 필요')
                    if entered and start:start=max(start,entered)
                    if exited and end:end=min(end,exited)
                    deposit=optional_money(row[12]);rent=optional_money(row[13]);annual=optional_money(row[15])
                    term=clean(row[14]);basis='원자료 연 임대수익'
                    if annual is None:
                        if term=='월납' and rent is not None:annual=rent*12;basis='월납 임대료 × 12'
                        elif term=='분기납' and rent is not None:annual=rent*4;basis='분기납 임대료 × 4'
                        elif term=='없음' and rent==0:annual=Decimal(0);basis='무상'
                        else:notes.append('연 임대수익/납부 기준 확인 필요')
                    if annual is not None and rent is not None and term in ('월납','분기납'):
                        expected=rent*(12 if term=='월납' else 4)
                        if expected!=annual:notes.append('납부액 환산과 연 임대수익 다름: 원자료 연액 적용')
                    if deposit is None:notes.append('보증금 미입력')
                    records.append(dict(group=group,number=number,tenant=clean(row[5]),representative=clean(row[6]),business=clean(row[7]),special=clean(row[16]),
                        building=clean(row[1]),floor=clean(row[2]),room=clean(row[3]),location=location_text(*row[1:4]),
                        raw_values={key:row[column-1] for key,column in EDIT_COLUMNS.items()},revision=revision,
                        start=start,end=end,exited=exited,period=clean(row[8]),deposit=deposit,rent=rent,annual=annual,monthly=annual/12 if annual is not None else None,
                        term=term,basis=basis,notes=' · '.join(notes),source=str(path),sheet=sheet.title,row=rn))
                except (ValueError,TypeError,ArithmeticError) as exc:
                    issues.append(f'{path.name} {sheet.title} {rn}행: {exc}')
        if not records:issues.append(f'{path.name}: 읽을 수 있는 임대 계약 내역이 없습니다.')
    finally:book.close()
    return records,issues


def load_rentals(folder):
    folder=Path(folder);records=[];issues=[]
    if not folder.exists():return [],['settings/contract에 임대사항_대학.xlsx, 임대사항_제네시스랩.xlsx를 저장하세요.']
    paths=sorted(p for p in folder.iterdir() if p.is_file() and p.stem.startswith('임대사항_') and p.suffix.lower() in ('.xlsx','.xlsm') and not p.name.startswith('~$'))
    seen=set()
    for path in paths:
        if path.stem in seen:
            raise ValueError(f'{path.stem}: 같은 구분의 파일이 중복됩니다. 하나만 남겨 주세요.')
        seen.add(path.stem)
        rows,notes=read_rentals(path);records.extend(rows);issues.extend(notes)
    return records,issues


def status(record,asof):
    if record.get('exited') and asof>=record['exited']:return '만료/퇴거'
    if not record['start'] or not record['end']:return '기간 확인'
    if asof<record['start']:return '예정'
    if asof>record['end']:return '만료/퇴거'
    return '유효'


def month_income(record,year,month):
    if not record['start'] or not record['end']:return None
    first=date(year,month,1);days=calendar.monthrange(year,month)[1];last=date(year,month,days)
    start=max(first,record['start']);end=min(last,record['end'])
    if end<start:return Decimal(0)
    if record['monthly'] is None:return None
    return record['monthly']*Decimal((end-start).days+1)/days


def forecasts(records,year):
    rows=[]
    for month in range(1,13):
        values=[month_income(r,year,month) for r in records]
        rows.append([f'{month}월',sum((v for v in values if v is not None),Decimal(0)),sum(v is None for v in values)])
    return rows


PDF_GROUPS={'대학':'campus','제네시스랩':'genesislab'}
EXPIRED_FOLDER='contract-expried'


def contract_pdfs(settings,record,*,include_archive=True):
    subfolder=PDF_GROUPS.get(record['group'])
    if subfolder is None or record['number'] is None:return []
    settings=Path(settings)
    folders=(settings/'contract'/subfolder,settings/('contract-'+subfolder),settings/'contract'/('contract-'+subfolder))
    if include_archive:folders+=(settings/EXPIRED_FOLDER/subfolder,)
    pattern=re.compile(r'^\s*0*'+str(record['number'])+r'\s*\.\s*.+',re.I)
    return sorted({p.resolve() for folder in folders if folder.exists() for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower()=='.pdf' and pattern.match(p.stem)})


@contextmanager
def archive_exit_pdfs(settings,record,exit_date):
    """Move matching PDFs together with the workbook save, rolling back on failure."""
    sources=contract_pdfs(settings,record,include_archive=False) if exit_date else []
    moved=[]
    try:
        for source in sources:
            folder=settings/EXPIRED_FOLDER/PDF_GROUPS[record['group']]
            folder.mkdir(parents=True,exist_ok=True)
            target=folder/source.name
            suffix=1
            while True:
                try:
                    target.open('xb').close()
                    break
                except FileExistsError:
                    suffix+=1
                    target=folder/f'{source.stem} ({suffix}){source.suffix}'
            try:source.replace(target)
            except OSError:
                target.unlink()
                raise
            moved.append((source,target))
        yield
    except Exception:
        for source,target in reversed(moved):target.rename(source)
        raise


HEADERS=['계약번호','구분','임대사항(위치)','업체명','대표자명','사업자등록번호','임대기간','상태','임대보증금','월 환산 임대료','연 임대수익','납부구분','계약서 보기','특이사항']
AMOUNT_COLUMNS = {HEADERS.index(title): key for title, key in (
    ('임대보증금', 'deposit'), ('월 환산 임대료', 'monthly'), ('연 임대수익', 'annual'),
)}


def rounded_won(value):
    return None if value is None else Decimal(value).quantize(Decimal(1),rounding=ROUND_HALF_UP)


def table_rows(records,asof):
    return [[r['number'],r['group'],r['location'],r['tenant'],r['representative'],r['business'],r['period'],status(r,asof),r['deposit'],rounded_won(r['monthly']),r['annual'],r['term'],'',r.get('special','')] for r in records]


def table_totals(records):
    totals = [''] * len(HEADERS)
    totals[HEADERS.index('임대사항(위치)')] = '확인금액 합계'
    for column, key in AMOUNT_COLUMNS.items():
        totals[column] = rounded_won(sum((r[key] for r in records if r[key] is not None), Decimal(0)))
    return totals


def export_rentals(target,records,asof,year,issues):
    book=Workbook();sheet=book.active;sheet.title='임대사항';append_row(sheet,HEADERS)
    for row in table_rows(records,asof):append_row(sheet,row)
    append_row(sheet,table_totals(records))
    monthly=book.create_sheet('월별 예상 수익');append_row(monthly,['월','예상 수익(원)','계산 제외 건수'])
    projection=forecasts(records,year)
    for row in projection:append_row(monthly,row)
    append_row(monthly,['연 합계',sum((r[1] for r in projection),Decimal(0))])
    criteria=book.create_sheet('산정 기준')
    for row in [('기준일',asof.isoformat()),('예상 연도',year),('계산','원자료 연 임대수익 우선 / 월 환산=연액÷12 / 계약 유효일수÷월 일수로 월별 안분'),
                ('한계','달력연도 기준, 자동 갱신·실제 수납·부가세 가감 미반영. 보증금은 장부 기재액이며 반환 여부 미확인.'),
                *[('자료 확인',note) for note in issues]]:append_row(criteria,row)
    for r in records:append_row(criteria,[r['source'],r['sheet'],r['row'],r['basis'],r['notes']])
    for sheet in book:format_sheet(sheet)
    return save_atomic(book,target)

EDIT_COLUMNS={'building':2,'floor':3,'room':4,'tenant':6,'representative':7,'business':8,
              'period':9,'entered':10,'renewed':11,'exited':12,'deposit':13,'rent':14,'term':15,'annual':16,'special':17}


def location_text(building,floor,room):
    def suffix(value,unit):
        if isinstance(value,float) and value.is_integer():value=int(value)
        text=clean(value)
        return text if not text or text.endswith(unit) else text+unit
    return ' '.join(part for part in (clean(building),suffix(floor,'층'),suffix(room,'호')) if part)


def grouped_forecasts(records,year,group='전체'):
    groups=['대학','제네시스랩'] if group=='전체' else [group]
    data={g:forecasts([r for r in records if r['group']==g],year) for g in groups}
    monthly=[[f'{m+1}월',*[data[g][m][1] for g in groups]] for m in range(12)]
    annual=[[str(year),*[sum((row[1] for row in data[g]),Decimal(0)) for g in groups]]]
    return ['월',*groups],monthly,annual


def update_rental(record,changes):
    """Update only edited cells, retaining formulas/styles; reject stale snapshots."""
    import os
    import tempfile
    from uuid import uuid4
    from openpyxl.cell.cell import MergedCell
    path=Path(record['source']);original=path.read_bytes()
    if hashlib.sha256(original).hexdigest()!=record['revision']:
        raise ValueError('원자료가 변경되었습니다. 새로고침 후 다시 수정하세요.')
    if not changes:return None
    if not set(changes)<=set(EDIT_COLUMNS):raise ValueError('수정할 수 없는 항목입니다.')
    converted=validate_changes(changes)
    book=load_workbook(BytesIO(original),keep_vba=path.suffix.lower()=='.xlsm')
    temporary=None
    try:
        sheet=book[record['sheet']];rn=record['row']
        for key,value in converted.items():
            cell=sheet.cell(rn,EDIT_COLUMNS[key])
            if isinstance(cell,MergedCell):raise ValueError('병합된 항목은 원자료에서 수정하세요.')
            cell.value=value
            if isinstance(value,str):cell.data_type='s'
            if key in ('deposit','rent','annual'):cell.number_format='#,##0.##########'
            if key in ('entered','renewed','exited') and value is not None:cell.number_format='yyyy-mm-dd'
        # Keep the original register's existing totals in sync with edited monetary cells.
        for row in sheet:
            if re.sub(r'\s+','',clean(row[0].value)) not in ('합계','총계'):continue
            for key in ('deposit','rent','annual'):
                column=EDIT_COLUMNS[key]
                if key not in converted or sheet.cell(row[0].row,column).value is None:continue
                from openpyxl.utils import get_column_letter
                letter=get_column_letter(column)
                refs=[f'{letter}{i}' for i in range(3,sheet.max_row+1) if sheet.cell(i,6).value]
                sheet.cell(row[0].row,column).value='=SUM('+','.join(refs)+')' if refs else 0
        fd,temporary=tempfile.mkstemp(dir=path.parent,suffix=path.suffix);os.close(fd)
        book.save(temporary)
        from rental_formulas import restore_formula_caches
        restore_formula_caches(temporary,original,book,sheet.title,bool(set(converted)&{'deposit','rent','annual'}))
        if path.read_bytes()!=original:raise ValueError('저장 중 원자료가 변경되었습니다. 새로고침 후 다시 수정하세요.')
        backup_dir=path.parent/'backups';backup_dir.mkdir(exist_ok=True)
        backup=backup_dir/f'{path.stem}_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex[:6]}{path.suffix}'
        with backup.open('xb') as out:out.write(original)
        with archive_exit_pdfs(path.parent.parent,record,converted.get('exited')):
            os.replace(temporary,path);temporary=None
        return backup
    finally:
        book.close()
        if temporary and os.path.exists(temporary):os.unlink(temporary)


def validate_changes(changes):
    converted={}
    for key,value in changes.items():
        text=clean(value)
        if key in ('deposit','rent','annual'):
            converted[key]=optional_money(value)
            if converted[key] is not None and converted[key]<0:raise ValueError('금액은 0 이상으로 입력하세요.')
        elif key in ('entered','renewed','exited'):
            parsed=parse_date(value)
            if text and parsed is None:raise ValueError('날짜는 YYYY-MM-DD 형식으로 입력하세요.')
            converted[key]=parsed
        elif key=='period':
            period=re.split(r'\s*[~～]\s*',text)
            dates=[parse_date(v) for v in period]
            if len(dates)!=2 or any(d is None for d in dates) or dates[0]>dates[1]:
                raise ValueError('임대기간은 YYYY-MM-DD ~ YYYY-MM-DD 형식으로 입력하세요.')
            converted[key]=text
        else:
            if key=='tenant' and not text:raise ValueError('업체명은 비워둘 수 없습니다.')
            converted[key]=text or None
    return converted


def create_rental(folder,group,values,number=None):
    """Insert a new contract before totals; allocate its number at save time."""
    import os
    import tempfile
    from copy import copy
    from uuid import uuid4
    from openpyxl.formula.translate import Translator
    from openpyxl.utils import get_column_letter
    if group not in ('대학','제네시스랩'):raise ValueError('대학 또는 제네시스랩을 선택하세요.')
    if not set(values)<=set(EDIT_COLUMNS):raise ValueError('입력할 수 없는 항목입니다.')
    converted=validate_changes(dict(values,tenant=values.get('tenant',''),period=values.get('period','')))
    folder=Path(folder)
    paths=[p for p in folder.glob(f'임대사항_{group}.*') if p.suffix.lower() in ('.xlsx','.xlsm')]
    if len(paths)>1:raise ValueError('같은 구분의 원자료가 중복됩니다. 하나만 남겨 주세요.')
    path=paths[0] if paths else folder/f'임대사항_{group}.xlsx'
    original=path.read_bytes() if path.exists() else None
    if original is None:
        book=Workbook();sheet=book.active;sheet.title=group
        sheet.append(['번호','임대사항',None,None,'임대면적(㎡)','임차인 인적사항 및 임대차 계약내용',None,None,None,None,None,None,None,None,'비고','연 임대수익','특이사항'])
        sheet.append([None,'동','층','호',None,'업체명','대표자명','사업자등록번호','임대기간','입주일','갱신일','퇴거일','임대보증금','임대료'])
        sheet.freeze_panes='F3'
        cache_source=BytesIO();book.save(cache_source);cache_source=cache_source.getvalue()
    else:
        book=load_workbook(BytesIO(original),keep_vba=path.suffix.lower()=='.xlsm')
        matches=[s for s in book if [s.cell(2,c).value for c in (6,9,13,14)]==['업체명','임대기간','임대보증금','임대료']]
        if len(matches)!=1:book.close();raise ValueError('원자료에 임대사항 표를 하나만 준비하세요.')
        sheet=matches[0];cache_source=original
    temporary=None
    try:
        occupied=[r for r in range(3,sheet.max_row+1) if sheet.cell(r,6).value]
        used=set()
        for row_number in occupied:
            text=clean(sheet.cell(row_number,1).value)
            if re.fullmatch(r'[1-9]\d*(?:\.0+)?',text):used.add(int(Decimal(text)))
        if number is None or clean(number)=='':new_number=max(used,default=0)+1
        else:
            if not re.fullmatch(r'[1-9]\d*',str(number)):raise ValueError('계약번호는 양의 정수로 입력하세요.')
            new_number=int(number)
        if new_number in used:raise ValueError('이미 사용 중인 계약번호입니다.')
        rn=max(occupied,default=2)+1
        # Insert instead of overwriting totals, placeholders, or notes below the last contract.
        formulas={c.coordinate:c.value for row in sheet for c in row if c.data_type=='f' and c.row>=rn}
        ranges=[str(area) for area in sheet.merged_cells.ranges]
        for area in ranges:
            from openpyxl.worksheet.cell_range import CellRange
            cell_range=CellRange(area)
            if cell_range.min_row<rn<=cell_range.max_row:raise ValueError('추가 위치가 병합 영역 안에 있습니다. 원자료에서 병합을 확인하세요.')
        for area in ranges:
            if CellRange(area).min_row>=rn:sheet.unmerge_cells(area)
        sheet.insert_rows(rn)
        for area in ranges:
            cell_range=CellRange(area)
            if cell_range.min_row>=rn:
                cell_range.shift(row_shift=1);sheet.merge_cells(str(cell_range))
        for address,formula in formulas.items():
            old=sheet[address];destination=f'{old.column_letter}{old.row+1}'
            sheet[destination]=Translator(formula,origin=address).translate_formula(destination)
        if occupied:
            for col in range(1,18):
                sheet.cell(rn,col)._style=copy(sheet.cell(occupied[-1],col)._style)
        sheet.cell(rn,1).value=new_number
        for key,value in converted.items():
            cell=sheet.cell(rn,EDIT_COLUMNS[key]);cell.value=value
            if isinstance(value,str):cell.data_type='s'
            if key in ('deposit','rent','annual'):cell.number_format='#,##0.##########'
            if key in ('entered','renewed','exited') and value is not None:cell.number_format='yyyy-mm-dd'
        if converted.get('annual') is None:
            factor={'월납':12,'분기납':4,'없음':0}.get(converted.get('term'))
            if factor==0 and converted.get('rent')!=0:factor=None
            if factor is not None and converted.get('rent') is not None:
                sheet.cell(rn,16).value=f'=N{rn}*{factor}'
        for row in sheet:
            if re.sub(r'\s+','',clean(row[0].value)) not in ('합계','총계'):continue
            for column in (13,14,16):
                cell=sheet.cell(row[0].row,column)
                if cell.value is None:continue
                letter=get_column_letter(column)
                refs=[f'{letter}{i}' for i in range(3,sheet.max_row+1) if sheet.cell(i,6).value]
                cell.value='=SUM('+','.join(refs)+')'
        folder.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(dir=folder,suffix=path.suffix);os.close(fd)
        book.save(temporary)
        from rental_formulas import restore_formula_caches
        restore_formula_caches(temporary,cache_source,book,sheet.title,True)
        backup=None
        if original is not None:
            if path.read_bytes()!=original:raise ValueError('원자료가 변경되었습니다. 다시 저장하세요.')
            backup_dir=folder/'backups';backup_dir.mkdir(exist_ok=True)
            backup=backup_dir/f'{path.stem}_{datetime.now():%Y%m%d_%H%M%S_%f}_{uuid4().hex[:6]}{path.suffix}'
            with backup.open('xb') as output:output.write(original)
        with archive_exit_pdfs(folder.parent,{'group':group,'number':new_number},converted.get('exited')):
            if original is None:
                import shutil
                with path.open('xb') as output:
                    try:
                        with open(temporary,'rb') as source:shutil.copyfileobj(source,output)
                    except OSError:
                        output.close();path.unlink(missing_ok=True);raise
            else:
                os.replace(temporary,path);temporary=None
        return {'path':path,'number':new_number,'backup':backup}
    finally:
        book.close()
        if temporary and os.path.exists(temporary):os.unlink(temporary)
