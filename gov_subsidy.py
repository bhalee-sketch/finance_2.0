"""내장 국고보조금명세서의 연도별 결산액과 원본 Excel 읽기."""
import json
from pathlib import Path
import re
from decimal import Decimal
from openpyxl import load_workbook
from finance_data import money

CATEGORIES=['교육부(기타지원금)','교육부(국가장학금)','기타국고지원','지방자치단체']
BUNDLED_SUBSIDIES=Path(__file__).resolve().parent/'data'/'govsubsidy'/'statements.json'
_CACHE={}

def normalized(value):return re.sub(r'\s+','',str(value or ''))


def read_subsidy(path):
    book=load_workbook(path,read_only=True,data_only=True)
    try:
        candidates=[]
        for sheet in book:
            for rn,row in enumerate(sheet.iter_rows(max_row=20,values_only=True),1):
                names=[normalized(v) for v in row]
                if '계정과목' in names and '결산액' in names and any(v.startswith('사업명') for v in names):
                    candidates.append((sheet,rn,names.index('계정과목'),names.index('결산액'),next(i for i,v in enumerate(names) if v.startswith('사업명'))));break
        if len(candidates)!=1:raise ValueError(f'{path.name}: 계정과목·사업명·결산액 표를 하나만 준비하세요.')
        sheet,head,ci,ai,pi=candidates[0];sums={k:Decimal(0) for k in CATEGORIES};details=[]
        for rn,row in enumerate(sheet.iter_rows(min_row=head+1,values_only=True),head+1):
            category=normalized(row[ci]);project=str(row[pi] or '').strip()
            if category in ('합계','총계','소계') or project in ('합계','총계','소계'):continue
            if not category and not project:continue
            if not category or not project:raise ValueError(f'{path.name} {rn}행: 계정과목 또는 사업명 누락')
            if row[ai] is None or str(row[ai]).strip()=='':raise ValueError(f'{path.name} {rn}행: 결산액 누락/수식 계산값 없음')
            try:value=money(row[ai])
            except ValueError as e:raise ValueError(f'{path.name} {rn}행: {e}') from e
            sums[category]=sums.get(category,Decimal(0))+value
            details.append([category,project,value,sheet.title,rn])
        if not details:raise ValueError(f'{path.name}: 사업 내역이 없습니다.')
        return sums,len(details),details
    finally:book.close()


def load_bundled_subsidies():
    history={}
    with BUNDLED_SUBSIDIES.open(encoding='utf-8') as stream:
        records=json.load(stream)
    for year,record in records.items():
        sums=dict.fromkeys(CATEGORIES,Decimal(0))
        details=[]
        for category,project,amount,sheet,row in record['details']:
            value=Decimal(amount)
            sums[category]=sums.get(category,Decimal(0))+value
            details.append([category,project,value,sheet,row])
        history[year]={'amounts':sums,'count':len(details),'details':details,'source':record['source']}
    return history,[]


def load_subsidies(folder):
    folder=Path(folder)
    if not folder.exists():return {},['국고보조금명세서 폴더를 찾을 수 없습니다.']
    history={};issues=[];seen={}
    for path in sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.xlsx'):
        if path.name.startswith('~$'):continue
        years=set(re.findall(r'(?<!\d)(20\d{2})(?!\d)',path.stem))
        if len(years)!=1:issues.append(f'{path.name}: 파일명의 연도 확인 필요');continue
        year=years.pop()
        if year in seen:raise ValueError(f'{year}년 국고보조금 파일이 중복됩니다: {seen[year].name}, {path.name}')
        seen[year]=path
        try:
            stat=path.stat();key=(str(path.resolve()),stat.st_mtime_ns,stat.st_size)
            if key not in _CACHE:
                sums,count,details=read_subsidy(path)
                _CACHE[key]={'amounts':sums,'count':count,'details':details,'source':path}
            history[year]=_CACHE[key]
        except (ValueError,OSError) as e:issues.append(str(e))
    return history,issues


def subsidy_series(history):
    labels=list(CATEGORIES)
    for year,data in sorted(history.items(),reverse=True):
        for label in data['amounts']:
            if label not in labels:labels.append(label)
    return ['회계연도',*labels],[[year,*[data['amounts'].get(label,Decimal(0)) for label in labels]] for year,data in sorted(history.items())]
