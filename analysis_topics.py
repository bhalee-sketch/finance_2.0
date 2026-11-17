"""확보된 원자료로 계산하는 재무분석 주제별 데이터. 결측치를 0으로 만들지 않는다."""
from collections import defaultdict
from decimal import Decimal
from financial_analysis import denominator,analysis_rows,ratio
from analysis_presentation import complete_sum
from statement_analysis import normalize


def cash_topics(history,scope,unit,topic):
    selected={};labels=[]
    for year,data in sorted(history.items(),reverse=True):
        items=data['datasets'].get((scope,unit),{}).get('items',{}).values()
        found=[]
        for item in items:
            if item['level']!=2:continue
            path=item['path'];name=normalize(path[-1])
            if topic=='fund':
                if item['section']=='수입' and '기금인출' in name:label='기금 인출'
                elif item['section']=='지출' and ('기금적립' in name or '적립금' in name):label='기금 적립'
                else:continue
            else:
                if item['section']!='수입' or not any('국고보조금' in normalize(p) for p in path):continue
                label=path[-1]
            if label not in labels:labels.append(label)
            found.append((label,item))
        selected[year]=found
    if topic=='fund':labels=['기금 인출','기금 적립']
    rows=[];details=[]
    for year in sorted(history):
        found=selected[year]
        rows.append([year,*[complete_sum(item['actual'] for label,item in found if label==target) for target in labels]])
        details.extend([[year,label,' / '.join(item['path']),item['actual'],*item['source']] for label,item in found])
    return ['회계연도',*labels],rows,details


def expense_ratio(data,preset,scope,unit,path=()):
    value,details,note=denominator(data,preset)
    items,base=analysis_rows(data,None,scope,unit,'지출',path,value)
    rows=[[v['item']['path'][-1],v['values'][1],ratio(v['values'][1],value)] for v in items]
    return value,rows,details,note


def loan_trends(folder):
    from loan_manager import find_loan_files,read_rows,parse_date
    from finance_data import money
    groups=defaultdict(lambda:[Decimal(0)]*4);notes=[];sources=[]
    def year(date):return str(date.year-(date.month<3))
    for path in find_loan_files(folder):
        sources.append(str(path));rows,epoch=read_rows(path);found=False
        for index,row in enumerate(rows,1):
            due=parse_date(row[1],epoch);paid=parse_date(row[10],epoch)
            if not due and not paid:continue
            found=True
            try:principal=money(row[2]);interest=money(row[5])+money(row[16]);extra=money(row[15])
            except ValueError as e:raise ValueError(f'{path.name} {index}행: {e}') from e
            if due:
                groups[year(due)][0]+=principal;groups[year(due)][1]+=interest
            if paid:
                groups[year(paid)][2]+=principal+extra;groups[year(paid)][3]+=interest
        if not found:raise ValueError(f'{path.name}: 예정일(B열)·납부일(K열)을 확인하세요.')
    notes.append('예정은 예정일, 납부는 실제 납부일 기준 · 회계연도 3월~다음해 2월 · 원금 C/P열, 이자 F/Q열')
    return ['회계연도','예정 원금','예정 이자','납부 원금','납부 이자'],[[y,*v] for y,v in sorted(groups.items())],notes,sources


def expense_history(history,preset,scope,unit,basis='총액'):
    """연도별 관 지출/수입 분모. 분모를 초과해도 비율을 재정규화하지 않는다."""
    labels=[];selected={};notes=[]
    for year,data in sorted(history.items(),reverse=True):
        parsed=data.get('datasets',{}).get((scope,unit),{})
        items=[v for v in parsed.get('items',{}).values() if v['section']=='지출' and v['level']==0]
        for item in items:
            if item['path'][-1] not in labels:labels.append(item['path'][-1])
        if basis=='총액':denom=parsed.get('totals',{}).get('수입',(None,None))[1]
        else:
            denom,_,note=denominator(data,preset)
            if note:notes.append(f'{year}: {note}')
        selected[year]=(items,denom)
    rows=[];percentages=[]
    for year,(items,denom) in sorted(selected.items()):
        by_name={v['path'][-1]:v['actual'] for v in items}
        # A subject absent from this year's complete statement is not a missing cell.
        # Keep explicit None amounts and a missing denominator as missing.
        amounts=[by_name.get(label,Decimal(0) if items and denom is not None else None) for label in labels]
        rows.append([year,*amounts,denom])
        percentages.append([year,*[ratio(value,denom) for value in amounts]])
    return ['회계연도',*labels,'수입 분모'],rows,percentages,notes


def fund_balances(history,scope,unit):
    """재무상태표의 임의기금 목 잔액. 현금 인출/적립과 구분한다."""
    labels=[];selected={}
    for year,data in sorted(history.items(),reverse=True):
        parsed=data.get('statements',{}).get('재무상태표',{}).get((scope,unit),{})
        found={}
        for item in parsed.get('items',{}).values():
            name=normalize(item['path'][-1])
            if item['section']=='자산' and item['level']==2 and name.startswith('임의') and '기금' in name:
                label=item['path'][-1];found[label]=item['actual']
                if label not in labels:labels.append(label)
        selected[year]=found
    return ['회계연도',*labels],[[y,*[v.get(k) for k in labels]] for y,v in sorted(selected.items())]


def loan_dashboard(folder):
    """연도/분기 현황. 잔여 예정액은 미도래 일정의 합이며 대출원금 잔액이 아니다."""
    from loan_manager import find_loan_files,read_rows,parse_date,status_row
    from finance_data import money
    scheduled=defaultdict(lambda:[Decimal(0),Decimal(0)])
    paid=defaultdict(lambda:[Decimal(0),Decimal(0)])
    sources=[]
    def period(date):return (str(date.year-(date.month<3)),((date.month-3)%12)//3+1)
    for path in find_loan_files(folder):
        sources.append(str(path));rows,epoch=read_rows(path);found=False
        for index,row in enumerate(rows,1):
            due=parse_date(row[1],epoch);actual=parse_date(row[10],epoch)
            if not due and not actual:continue
            found=True
            try:p=money(row[2]);i=money(row[5])+money(row[16]);extra=money(row[15])
            except ValueError as e:raise ValueError(f'{path.name} {index}행: {e}') from e
            if due:
                scheduled[period(due)][0]+=p;scheduled[period(due)][1]+=i
            if actual:
                # 일정별 완료 판정은 해당 일정에 귀속. 실제 납부 추이는 실제 날짜 기준.
                paid[period(actual)][0]+=p+extra;paid[period(actual)][1]+=i
        if not found:raise ValueError(f'{path.name}: 예정일(B열)·납부일(K열)을 확인하세요.')
    years=sorted({y for y,q in scheduled}|{y for y,q in paid})
    annual=[];quarters={}
    for y in years:
        s=[sum((scheduled[y,q][i] for q in range(1,5)),Decimal(0)) for i in range(2)]
        p=[sum((paid[y,q][i] for q in range(1,5)),Decimal(0)) for i in range(2)]
        annual.append([y,*s,*p])
        quarters[y]=[status_row(f'{q}분기',scheduled[y,q],paid[y,q]) for q in range(1,5)]
        quarters[y].append(status_row('합계',s,p))
    return annual,quarters,sources
