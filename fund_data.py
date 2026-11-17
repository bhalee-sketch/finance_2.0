"""settings/fund/YYYY년 기금.xlsx(xlsm)의 기말잔액. 매크로는 실행하지 않는다."""
import re
from pathlib import Path
from decimal import Decimal
from openpyxl import load_workbook
from finance_data import money

HEADERS=['구분','내용','전기이월','당기증가','당기감소','기말잔액']
_CACHE={}

def norm(value):return re.sub(r'\s+','',str(value or ''))


def read_fund(path,year):
    book=load_workbook(path,read_only=True,data_only=True)
    try:
        matches=[]
        for sheet in book:
            for rn,row in enumerate(sheet.iter_rows(max_row=20,values_only=True),1):
                names=[norm(v) for v in row]
                if all(h in names for h in HEADERS):matches.append((sheet,rn,[names.index(h) for h in HEADERS]));break
        if len(matches)!=1:raise ValueError(f'{path.name}: 구분·내용·기말잔액 표를 하나만 준비하세요.')
        sheet,head,indices=matches[0];amounts={};details=[];notes=[]
        sheet_years=re.findall(r'(?<!\d)(20\d{2})(?!\d)',sheet.title)
        if sheet_years and year not in sheet_years:notes.append(f'{path.name}: 시트명 연도와 다름, 파일명 {year}년 기준 적용')
        for rn,row in enumerate(sheet.iter_rows(min_row=head+1,values_only=True),head+1):
            values=[row[i] if i<len(row) else None for i in indices]
            group,description=[str(v or '').strip() for v in values[:2]]
            if not any(v is not None for v in values):continue
            if any(norm(v) in ('합계','소계','총계','총합계') or norm(v).endswith(('소계','합계')) for v in values[:2]):continue
            if not group or not description:raise ValueError(f'{path.name} {rn}행: 구분 또는 내용 누락')
            if any(v is None or str(v).strip()=='' for v in values[2:]):raise ValueError(f'{path.name} {rn}행: 금액 누락/수식 계산값 없음')
            numbers=[money(v) for v in values[2:]]
            amounts[group]=amounts.get(group,Decimal(0))+numbers[-1]
            details.append([group,description,*numbers])
        if not details:raise ValueError(f'{path.name}: 기금 내역이 없습니다.')
        return {'amounts':amounts,'details':details,'source':path,'notes':notes}
    finally:book.close()


def load_funds(folder):
    folder=Path(folder);history={};issues=[];seen={}
    if not folder.exists():return {},['settings/fund에 YYYY년 기금.xlsx 또는 .xlsm 파일을 저장하세요.']
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith('~$') or path.suffix.lower() not in ('.xlsx','.xlsm'):continue
        match=re.fullmatch(r'(20\d{2})\s*년\s*기금',path.stem)
        if not match:continue
        year=match[1]
        if year in seen:raise ValueError(f'{year}년 기금 파일이 중복됩니다.')
        seen[year]=path
        try:
            stat=path.stat();key=(str(path.resolve()),stat.st_mtime_ns,stat.st_size)
            if key not in _CACHE:_CACHE[key]=read_fund(path,year)
            history[year]=_CACHE[key];issues.extend(history[year]['notes'])
        except (ValueError,OSError) as exc:issues.append(str(exc))
    return history,issues


def fund_series(history):
    labels=[]
    for year,data in sorted(history.items()):
        for label in data['amounts']:
            if label not in labels:labels.append(label)
    return ['회계연도',*labels],[[year,*[data['amounts'].get(label,Decimal(0)) for label in labels]] for year,data in sorted(history.items())]


def individual_fund_series(history,selected):
    """Stable identity is (category, description); do not merge equal names across categories."""
    labels=[f'{group} / {name}' for group,name in selected]
    rows=[]
    for year,data in sorted(history.items()):
        amounts={}
        for group,name,*numbers in data['details']:
            key=(group,name);amounts[key]=amounts.get(key,Decimal(0))+numbers[-1]
        rows.append([year,*[amounts.get(key,Decimal(0)) for key in selected]])
    return ['회계연도',*labels],rows
