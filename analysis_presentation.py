"""재무분석의 표시용 단위, 중복 없는 표 합계와 원형차트 데이터."""
from decimal import Decimal
from financial_analysis import ratio


def unit_label(value):return '전체' if value=='합계' else value


def available_units(data,scope):
    return [u for s,u in data['datasets'] if s==scope and (scope!='등록금' or u in ('합계','교비','대학원'))]


def complete_sum(values):
    values=list(values)
    return sum(values,Decimal(0)) if values and all(v is not None for v in values) else None


def analysis_total(rows,base,denominator):
    a=complete_sum(r['values'][1] for r in rows);b=complete_sum(r['values'][4] for r in rows)
    delta=a-b if a is not None and b is not None else None
    return ['표시 과목 합계',a,ratio(a,base),ratio(a,denominator),b,delta,ratio(delta,b),'누락값 포함 시 해당 합계 공란 · 원본 총계와 다를 수 있음']


def trend_total(rows):
    a=complete_sum(r[1] for r in rows);b=complete_sum(r[2] for r in rows)
    return ['조회 연도 합계',a,b,ratio(a,b)]


def pie_values(rows):
    return [(r['item']['path'][-1],r['values'][1]) for r in rows if r['values'][1] is not None and r['values'][1]>0]


def expand_to_mok(parsed,paths):
    """기존 관/항 조합을 해당 수입 목으로 펼친다. 저장 전 사용자가 확인한다."""
    from statement_analysis import normalize
    prefixes=[tuple(map(normalize,p)) for p in paths]
    return [list(item['path']) for item in parsed.get('items',{}).values()
            if item['section']=='수입' and item['level']==2
            and any(tuple(map(normalize,item['path']))[:len(p)]==p for p in prefixes)]


def multi_trend(history,years,scope,unit,section,paths):
    from statement_analysis import normalize
    all_years=set(history)|set(years)
    names=[p[-1] for p in paths]
    labels=[' / '.join(p) if names.count(p[-1])>1 else p[-1] for p in paths]
    rows=[]
    if not all_years:return ['연도',*labels],rows
    for number in range(min(map(int,all_years)),max(map(int,all_years))+1):
        year=str(number);parsed=history.get(year,{}).get('datasets',{}).get((scope,unit),{})
        row=[year]
        for path in paths:
            if path[0]=='__total__':
                row.append(parsed.get('totals',{}).get(path[1],(None,None))[1]);continue
            found=[v['actual'] for v in parsed.get('items',{}).values() if v['section']==section and tuple(map(normalize,v['path']))==tuple(map(normalize,path))]
            row.append(found[0] if len(found)==1 else None)
        rows.append(row)
    return ['연도',*labels],rows


def source_total_row(current,previous,scope,unit,section,statement):
    """원본 총계만 표시한다. 현재 보이는 과목을 합산하지 않는다."""
    parsed=current.get('datasets',{}).get((scope,unit),{})
    prior=(previous or {}).get('datasets',{}).get((scope,unit),{})
    value=parsed.get('totals',{}).get(section,(None,None))[1]
    before=prior.get('totals',{}).get(section,(None,None))[1]
    label=({'수입':'자금수입총계','지출':'자금지출총계'} if statement=='자금계산서' else
           {'자산':'자산총계','부채와기본금':'부채와기본금총계'} if statement=='재무상태표' else
           {'수입':'운영수익총계','지출':'운영비용총계'}).get(section,'원본 총계')
    return [label,value,Decimal(100) if value is not None and value>0 else None,
            value-before if value is not None and before is not None else None]


def expanded_composition(current,previous,scope,unit,section,path,denom,expanded,depth):
    """선택한 관을 하위 항/목으로 교체. 다른 관과 원본 순서를 보존한다."""
    from financial_analysis import analysis_rows
    rows,base=analysis_rows(current,previous,scope,unit,section,path,denom)
    result=[]
    for row in rows:
        parent=row['item']['path']
        if parent not in expanded or len(parent)!=1:
            result.append(row);continue
        children,_=analysis_rows(current,previous,scope,unit,section,parent,denom)
        if depth==2:
            leaves=[]
            for child in children:
                nested,_=analysis_rows(current,previous,scope,unit,section,child['item']['path'],denom)
                leaves.extend(nested or [child])
            children=leaves
        result.extend(children or [row])
    return result,base
