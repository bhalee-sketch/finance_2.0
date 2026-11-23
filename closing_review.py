"""Registration-account carryover screening under an explicit advance-payment assumption."""
from decimal import Decimal,InvalidOperation
from statement_analysis import parse_fund,normalize,optional_money


def review_carryover(record):
    issues=[]
    fund=parse_fund(record,'등록금')
    def fund_value(path):
        found=[item['actual'] for item in fund['items'].values() if item['section']=='지출' and tuple(normalize(p) for p in item['path'])==path]
        if len(found)!=1 or found[0] is None:
            issues.append('자금계산서 금액 확인: '+' / '.join(path));return None
        return found[0]
    prefix=('미사용차기이월자금',)
    carry=fund_value(prefix)
    details=[]
    for group,names in [('기말유동자산',('유동자금','기타유동자산')),('기말유동부채',('예수금','선수금','기타유동부채'))]:
        for name in names:details.append((group,name,fund_value(prefix+(group,name))))
        details.append((group,'계',fund_value(prefix+(group,))))
    income=fund['totals'].get('수입',(None,None))[1]
    if income is None or income<=0:issues.append('자금계산서 수입총액은 양수여야 합니다.')
    balance={}
    sheets=[s for s in record['sheets'] if normalize(s['name'])=='재무상태표(등록금)']
    if len(sheets)!=1:issues.append('재무상태표(등록금) 시트를 하나만 준비하세요.')
    else:
        sheet=sheets[0];headers=[normalize(h) for h in sheet['headers']]
        if headers.count('당기')!=1:issues.append('재무상태표 당기 열을 확인하세요.')
        else:
            index=headers.index('당기');path=['','','']
            wanted={('유동자산',),('유동부채',),('유동자산','기타유동자산','선급금')}
            for row in sheet['rows']:
                raw=str(row[0] or '') if row else ''
                if not raw.strip():continue
                indent=len(raw)-len(raw.lstrip(' '));level=0 if indent<5 else 1 if indent<10 else 2
                path[level]=normalize(raw)
                for j in range(level+1,3):path[j]=''
                key=tuple(path[:level+1])
                if key not in wanted:continue
                if key in balance:raise ValueError('재무상태표에 동일 과목이 중복됩니다: '+' / '.join(key))
                value=str(row[index] if index<len(row) else '').strip().replace(',','')
                try:
                    amount=Decimal(value)
                    if not amount.is_finite():raise InvalidOperation
                except InvalidOperation:amount=None
                balance[key]=amount
            for key in wanted:
                if balance.get(key) is None:issues.append('재무상태표 금액 확인: '+' / '.join(key))
    advance=balance.get(('유동자산','기타유동자산','선급금'))
    assets=balance.get(('유동자산',));liabilities=balance.get(('유동부채',))
    if None not in (assets,liabilities,carry) and assets-liabilities!=carry:issues.append('재무상태표 유동자산−유동부채와 미사용 차기이월자금이 다릅니다.')
    for group in ('기말유동자산','기말유동부채'):
        rows=[r for r in details if r[0]==group];total=rows[-1][2];parts=[r[2] for r in rows[:-1]]
        if total is not None and all(v is not None for v in parts) and sum(parts)!=total:issues.append(group+' 상세 합계가 원본 계와 다릅니다.')
    fa=details[2][2];fl=details[-1][2]
    if None not in (fa,fl,carry) and fa-fl!=carry:issues.append('자금계산서 기말유동자산−기말유동부채와 이월자금이 다릅니다.')
    if None not in (fa,assets) and fa!=assets:issues.append('두 재무제표의 기말유동자산이 다릅니다.')
    if None not in (fl,liabilities) and fl!=liabilities:issues.append('두 재무제표의 기말유동부채가 다릅니다.')
    other=carry-advance if None not in (carry,advance) else None
    if carry is not None and carry<0:issues.append('미사용 차기이월자금이 음수입니다.')
    if advance is not None and advance<0:issues.append('선급금이 음수입니다.')
    if other is not None and other<0:issues.append('선급금이 미사용 차기이월자금보다 큽니다.')
    ratio=other/income*100 if not issues and other is not None and income is not None and income>0 else None
    return dict(details=details,carryover=carry,advance=advance,income=income,other=other,ratio=ratio,
                limit=income*Decimal('.01') if income is not None and income>0 else None,
                state='자료 확인 필요' if ratio is None else '1.0% 이내' if ratio<=1 else '1.0% 초과',issues=issues)


def review_fund_transfers(record,scope='전체'):
    """Compare original fund subtotals, never sum them with their child accounts."""
    try:fund=parse_fund(record,scope);fund_error=None
    except ValueError as exc:fund=None;fund_error=str(exc)
    sheets=[s for s in record['sheets'] if normalize(s['name'])==f'운영계산서({scope})']
    results=[]
    for section,target,aliases in [('수입','운영차액대체',{'임의기금','임의기금인출수입'}),('지출','기본금대체액',{'임의기금','임의기금적립'})]:
        notes=[];source_value=None;target_value=None
        if fund is None:notes.append(fund_error)
        else:
            found=[item['actual'] for item in fund['items'].values() if item['section']==section and item['level']==1 and normalize(item['path'][-1]) in aliases]
            if len(found)!=1 or found[0] is None:notes.append(f'자금계산서 {section} 임의기금(항) 누락·중복 또는 금액 없음')
            else:source_value=found[0]
        if len(sheets)!=1:notes.append(f'운영계산서({scope}) 시트 누락 또는 중복')
        else:
            sheet=sheets[0];headers=[normalize(h) for h in sheet['headers']]
            if headers.count('당기')!=1:notes.append('운영계산서 당기 열 누락 또는 중복')
            else:
                idx=headers.index('당기');rows=[r for r in sheet['rows'] if r and normalize(r[0])==target]
                if len(rows)!=1:notes.append(target+' 과목 누락 또는 중복')
                else:
                    raw=rows[0][idx] if idx<len(rows[0]) else None
                    try:
                        from statement_analysis import optional_money
                        target_value=optional_money(raw)
                        if target_value is None:notes.append(target+' 당기 금액 없음')
                    except ValueError:notes.append(target+' 당기 금액 형식 확인 필요')
        diff=source_value-target_value if source_value is not None and target_value is not None else None
        results.append(dict(section=section,target=target,source=source_value,amount=target_value,difference=diff,
                            state='자료 확인 필요' if notes or diff is None else '일치' if diff==0 else '불일치',notes=notes))
    return results

STATEMENT_TOTAL_CHECKS=(
    ('자금계산서','결산',('자금수입총계','수입총계'),('자금지출총계','지출총계')),
    ('재무상태표','당기',('자산총계',),('부채와기본금총계','부채및기본금총계','부채와자본금총계','부채및자본금총계')),
    ('운영계산서','당기',('운영수익총계',),('비용총계','운영지출총계')),
)


def review_statement_totals(record):
    """Compare the reported grand totals in each consolidated statement."""
    results=[]
    for name,column,left_labels,right_labels in STATEMENT_TOTAL_CHECKS:
        sheets=[sheet for sheet in record['sheets'] if normalize(sheet['name'])==f'{name}(전체)']
        sheet=sheets[0] if len(sheets)==1 else {}
        headers=[normalize(header) for header in sheet.get('headers',())]
        index=headers.index(column) if headers.count(column)==1 else None

        def read_total(labels):
            if index is None:return None
            rows=[row for row in sheet['rows'] if row and normalize(row[0]).strip('[]') in labels]
            if len(rows)!=1 or index>=len(rows[0]):return None
            try:return optional_money(rows[0][index])
            except ValueError:return None

        left,right=read_total(left_labels),read_total(right_labels)
        difference=left-right if left is not None and right is not None else None
        state='자료 확인 필요' if difference is None else '일치' if difference==0 else '불일치'
        results.append((name,state,difference,left_labels[0],left,right_labels[0],right))
    return results
