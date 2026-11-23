"""Reserve limits using user-specified account mappings; no inferred investment balances."""
from decimal import Decimal
from pathlib import Path
from openpyxl import load_workbook
from statement_analysis import normalize
from finance_data import money,discover_ledger_years,load_ledger
from statement_catalog import discover_appendices
from statement_loader import load_statement_record_from_path
from fund_data import load_bundled_funds


def current_amount(record,subject,level):
    sheets=[s for s in record['sheets'] if normalize(s['name'])=='재무상태표(전체)']
    if len(sheets)!=1:raise ValueError('재무상태표(전체)를 하나만 준비하세요.')
    sheet=sheets[0];headers=[normalize(h) for h in sheet['headers']]
    if headers.count('당기')!=1:raise ValueError('재무상태표 당기 열을 확인하세요.')
    index=headers.index('당기');found=[]
    for row in sheet['rows']:
        raw=str(row[0] or '') if row else '';indent=len(raw)-len(raw.lstrip(' '));depth=0 if indent<5 else 1 if indent<10 else 2
        if normalize(raw)==subject and depth==level:
            value=row[index] if index<len(row) else None
            if value is None or str(value).strip() in ('','-'):raise ValueError(subject+' 당기 금액 누락')
            found.append(money(value))
    if len(found)!=1:raise ValueError(subject+' 과목 누락 또는 중복')
    return found[0]


def depreciation(path):
    if path is None:raise ValueError('운영계산서 부속명세서가 없습니다.')
    book=load_workbook(path,data_only=True,read_only=True)
    try:
        sheets=[s for s in book if normalize(s.title)=='고정자산감가상각비명세서']
        if len(sheets)!=1:raise ValueError('고정자산 감가상각비명세서를 하나만 준비하세요.')
        rows=list(sheets[0].iter_rows(values_only=True));indices=[]
        for row in rows[:10]:indices.extend(i for i,v in enumerate(row) if normalize(v)=='당기증가액')
        if len(indices)!=1:raise ValueError('감가상각비명세서 당기증가액 열을 확인하세요.')
        matches=[r for r in rows if any(normalize(v)=='건물' for v in r[:2])]
        if len(matches)!=1:raise ValueError('감가상각비명세서 건물 행을 확인하세요.')
        value=matches[0][indices[0]]
        if value is None or str(value).strip() in ('','-'):raise ValueError('건물 당기 감가상각비 계산값이 없습니다.')
        return money(value)
    finally:book.close()


def securities_principal(path):
    if path is None:raise ValueError('재무상태표 부속명세서가 없습니다.')
    book=load_workbook(path,data_only=True,read_only=True)
    try:
        sheets=[s for s in book if normalize(s.title)=='적립기금유가증권투자명세서']
        if len(sheets)!=1:raise ValueError('적립기금 유가증권 투자 명세서를 하나만 준비하세요.')
        rows=list(sheets[0].iter_rows(values_only=True));headers=[]
        for rn,row in enumerate(rows[:20]):
            for col,value in enumerate(row):
                if normalize(value)=='투자원금':headers.append((rn,col))
        if len(headers)!=1:raise ValueError('투자원금 열 누락 또는 중복')
        header,col=headers[0]
        totals=[r for r in rows[header+1:] if any(normalize(v)=='합계' for v in r[:col])]
        if len(totals)!=1:raise ValueError('투자원금 합계 행 누락 또는 중복')
        value=totals[0][col]
        if value is None or str(value).strip() in ('','-'):raise ValueError('투자원금 합계 계산값이 없습니다.')
        return money(value)
    finally:book.close()


def load_reserves(settings,year,statement,*,ledger_loader=None,statement_record=None):
    settings=Path(settings);values={};sources={};issues=[]
    def read(key,task,source):
        try:values[key]=task();sources[key]=source
        except Exception as exc:values[key]=None;issues.append(f'{key}: {exc}')
    record=load_statement_record_from_path(statement) if statement_record is None else statement_record
    read('reserve_total',lambda:current_amount(record,'임의적립금',1),str(statement)+' · 전체/임의적립금(항)/당기')
    read('building_reserve',lambda:current_amount(record,'임의건축적립금',2),str(statement)+' · 전체/임의건축적립금(목)/당기')
    def transferred():
        if ledger_loader is None:
            path=discover_ledger_years(settings/'lodges').get(str(year))
            if path is None:raise ValueError('선택연도 원장 없음')
            records=load_ledger(path,with_provenance=True)
        else:path,records=ledger_loader(settings,year)
        rows=[r for r in records if normalize(r['목'])=='등록금회계전입금']
        sources['transfer_rows']=rows;sources['transfer_file']=str(path)
        # No netting or absolute value: exactly the sum of credits requested.
        return sum((r['대변'] for r in rows),Decimal(0))
    read('transfer',transferred,'선택연도 원장 · 등록금회계전입금(목) 대변 합계')
    def fund_amount():
        history,_=load_bundled_funds();fund=history.get(str(year))
        if fund is None:raise ValueError(f'{year}년 내장 기금 자료가 없습니다.')
        rows=[row for row in fund['details'] if normalize(row[0])=='임의건축기금' and normalize(row[1])=='건축기금(감가상각)']
        if len(rows)!=1:raise ValueError('임의건축기금 / 건축기금(감가상각) 내역 누락 또는 중복')
        sources['fund_file']=str(fund['source']);return rows[0][-1]
    read('tuition_reserve',fund_amount,'기금 현황 · 임의건축기금/건축기금(감가상각) · 기말잔액')
    def building_depreciation():
        path=discover_appendices(statement)['운영계산서'];sources['depreciation_file']=str(path) if path else ''
        return depreciation(path)
    read('depreciation',building_depreciation,'운영계산서 부속명세서 · 고정자산 감가상각비명세서 · 건물/당기증가액')
    def investment():
        path=discover_appendices(statement)['재무상태표'];sources['securities_file']=str(path) if path else ''
        return securities_principal(path)
    read('securities',investment,'재무상태표 부속명세서 · 적립기금 유가증권 투자 명세서 · 투자원금/합계')
    return {'values':values,'sources':sources,'issues':issues}


def calculate(values,securities=None,venture=None):
    total=values.get('reserve_total');tuition=values.get('tuition_reserve');building=values.get('building_reserve')
    transfer=values.get('transfer');dep=values.get('depreciation')
    base=total-tuition if total is not None and tuition is not None else None
    other_building=building-tuition if building is not None and tuition is not None else None
    valid_base=base is not None and base>=0 and total>=0 and tuition>=0
    # Separate checks: a missing depreciation source must not conceal an investment excess.
    cap_state='자료 확인 필요' if dep is None or transfer is None or dep<0 or transfer<0 else '한도 이내' if transfer<=dep else '한도 초과'
    results={}
    for key,amount,fraction in [('securities',securities,Decimal('.5')),('venture',venture,Decimal('.1'))]:
        limit=base*fraction if valid_base else None
        ratio=amount/base*100 if valid_base and base>0 and amount is not None and amount>=0 else None
        state='자료 확인 필요' if limit is None or amount is None or amount<0 else '한도 이내' if amount<=limit else '한도 초과'
        results[key]={'amount':amount,'limit':limit,'ratio':ratio,'state':state}
    return {'base':base,'other_building':other_building,'capital_state':cap_state,**results}
