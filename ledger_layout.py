"""보조원장 화면 폭 배분: 주요 열 우선, 금액 읽기 폭 유지."""
COMPACT_COLUMNS=['회계일자','전표번호','목','차변','대변','거래선명','적요','재원']


def fit_ledger_columns(columns,measured,available):
    minimum={'회계일자':90,'전표번호':105,'목':80,'차변':100,'대변':100,'거래선명':85,'적요':150,'재원':75}
    caps={'적요':380,'거래선명':160,'전표번호':150,'목':150,'재원':160}
    lows=[];preferred=[]
    for name,value in zip(columns,measured):
        low=minimum.get(name,55)
        if name in ('차변','대변'):low=max(low,value)
        lows.append(low);preferred.append(max(low,min(value,caps.get(name,130))))
    available=max(0,int(available));floor=sum(lows);target=max(floor,available)
    room=target-floor;desired=[max(0,p-m) for p,m in zip(preferred,lows)]
    total=sum(desired)
    if total and room<total:
        result=[low+int(room*extra/total) for low,extra in zip(lows,desired)]
    else:
        result=preferred[:]
    remainder=target-sum(result)
    if remainder>0 and result:
        # 남는 폭은 적요에 배분하고 짧은 식별 열은 늘리지 않는다.
        index=columns.index('적요') if '적요' in columns else len(columns)-1
        result[index]+=remainder
    return result
