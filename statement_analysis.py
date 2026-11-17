"""자금계산서 결산 분석: 원본 총계와 계층별 과목을 분리해 이중 합산을 피한다."""
from decimal import Decimal
import re
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from finance_data import money, text, append_row, format_sheet, save_atomic

HEADERS=['과목 경로','예산','결산','결산-예산','집행률(%)','비교연도 결산','결산 증감','증감률(%)','양수 결산 구성비(%)','확인사항']
SUBTOTALS={'운영수입','운영지출','자산,부채및기본금수입','자산및부채수입','자산및부채지출','자산및부채및기본금수입','자산,부채수입','자산,부채지출'}

SUBTOTAL_KEYS={v.replace(',','').replace('·','') for v in SUBTOTALS}


def normalize(value):return re.sub(r'\s+','',text(value))


def optional_money(value):
    if not text(value) or text(value)=='-':return None
    return money(value)


def parse_fund(record,scope='전체'):
    sheets=[s for s in record['sheets'] if normalize(s['name'])==f'자금계산서({scope})']
    if len(sheets)!=1:raise ValueError(f'자금계산서({scope}) 시트를 하나만 준비하세요.')
    sheet=sheets[0];headers=[normalize(h) for h in sheet['headers']]
    if '결산' not in headers:raise ValueError('자금계산서 첫 행에 결산 열이 필요합니다.')
    budget_i=headers.index('예산') if '예산' in headers else None;actual_i=headers.index('결산')
    section='수입';path=['','',''];items={};totals={};divider=False;sources={}
    for number,row in enumerate(sheet['rows'],2):
        raw=str(row[0] or '') if row else '';name=raw.strip();key=normalize(name)
        if key.startswith('[지출]'):
            section='지출';path=['','',''];divider=True;continue
        if not name or name.startswith(('[','<','(')):continue
        def value(i):return optional_money(row[i] if i is not None and i<len(row) else None)
        budget,actual=value(budget_i),value(actual_i)
        if key in ('자금수입총계','자금지출총계'):
            totals['수입' if key=='자금수입총계' else '지출']=(budget,actual);continue
        if key.replace(',','').replace('·','') in SUBTOTAL_KEYS:continue
        indent=len(raw)-len(raw.lstrip(' '));level=0 if indent<5 else 1 if indent<10 else 2
        path[level]=name
        for j in range(level+1,3):path[j]=''
        if any(not v for v in path[:level]):raise ValueError(f'{sheet["name"]} {number}행: 관·항·목 들여쓰기 순서를 확인하세요.')
        identity=(section,level,tuple(path[:level+1]))
        item={'key':identity,'section':section,'level':level,'path':tuple(path[:level+1]),'budget':budget,'actual':actual}
        if identity in items:
            # 원본의 이월자금은 상세 전후에 같은 소계가 두 번 인쇄된다.
            if key in ('미사용전기이월자금','미사용차기이월자금') and items[identity]==item:continue
            raise ValueError(f'{sheet["name"]} {number}행: 동일 과목 경로가 중복됩니다 ({name}). 원본을 확인하세요.')
        items[identity]=item
        sources[identity]=number
    if not divider:raise ValueError('자금계산서의 [지출] 구분 행을 찾지 못했습니다.')
    return {'items':items,'totals':totals,'sheet':sheet['name'],'sources':sources}


def percent(numerator,denominator):
    return None if numerator is None or denominator is None or denominator<=0 else numerator/denominator*100


def compare(current,previous,section='지출',level=0):
    a={k:v for k,v in current['items'].items() if k[0]==section and k[1]==level}
    b={k:v for k,v in (previous or {}).get('items',{}).items() if k[0]==section and k[1]==level}
    positive=sum((v['actual'] for v in a.values() if v['actual'] is not None and v['actual']>0),Decimal(0))
    result=[]
    for k in list(a)+[key for key in b if key not in a]:
        now=a.get(k);before=b.get(k);budget=now['budget'] if now else None;actual=now['actual'] if now else None;prior=before['actual'] if before else None
        variance=None if actual is None or budget is None else actual-budget
        change=None if actual is None or prior is None else actual-prior
        notes=[]
        if now is None:notes.append('선택연도 과목 없음')
        elif actual is None:notes.append('결산 값 없음')
        if previous is None:notes.append('비교연도 미선택')
        elif before is None:notes.append('비교연도 과목 없음')
        if budget is None:notes.append('예산 값 없음')
        elif budget<=0:notes.append('집행률 산출 제외(예산≤0)')
        if actual is not None and actual<0:notes.append('음수 결산: 구성비 제외')
        result.append({'key':k,'values':[' / '.join(k[2]),budget,actual,variance,percent(actual,budget),prior,change,percent(change,prior),percent(actual,positive) if actual is not None and actual>0 else None,' · '.join(notes)]})
    return result


def export_analysis(current,previous,items,history,target,year,prior_year,scope,section,level):
    wb=Workbook();summary=wb.active;summary.title='분석 기준'
    for row in [['항목','내용'],['선택연도',year],['비교연도',prior_year or '미선택'],['회계단위',scope],['범위',section],['계층',level],
                ['기준','자금계산서의 예산·결산. 수입·지출은 현금 흐름이며 기업 손익과 다릅니다.'],
                ['집계','한 계층만 비교. 운영수입/지출 등 중간 합계와 반복 이월 소계 제외. 원본 총계 별도 표시.'],
                ['계층 주의','관·항·목은 서로 합산하지 않습니다. 이월자금의 자산·부채 상세는 순액 총계와 단순 합산이 다를 수 있습니다.'],
                ['산식','결산-예산 / 집행률=결산÷양수 예산 / 증감률=증감÷양수 비교결산 / 구성비=양수 결산÷표의 양수 결산 합'],
                ['결측','빈 값과 미존재 과목은 0으로 보정하지 않으며 관련 증감·비율은 비워 둡니다.'],
                ['비교 유의','동일한 관·항·목 경로만 연결합니다. 과목 개편·명칭 변경·회계정책 변경은 별도 확인하세요.'],
                ['활용','예산 검토·보고 참고자료입니다. 예산 승인 또는 감사 적정성을 자동 판정하지 않습니다.']]:append_row(summary,row)
    for label,(budget,actual) in current['totals'].items():append_row(summary,[f'{label} 원본 예산',budget]);append_row(summary,[f'{label} 원본 결산',actual])
    sheet=wb.create_sheet('과목별 분석');append_row(sheet,HEADERS)
    for row in items:append_row(sheet,row['values'])
    for row in sheet.iter_rows(min_row=2):
        for idx in (4,7,8):row[idx].number_format='0.0"%"'
    # 그래프용 표는 결산 절댓값 상위 12개만, 전체 내역은 과목별 분석에 보존한다.
    graph=wb.create_sheet('그래프');append_row(graph,['과목','예산','결산','결산 증감'])
    for item in items[:12]:
        v=item['values'];append_row(graph,[v[0],v[1],v[2],v[6]])
    if items:
        for title,lo,hi,anchor in [('예산 대비 결산',2,3,'F2'),('비교연도 대비 결산 증감',4,4,'F20')]:
            chart=BarChart();chart.type='bar';chart.title=title;chart.x_axis.title='원';chart.height=11;chart.width=25
            chart.add_data(Reference(graph,min_col=lo,max_col=hi,min_row=1,max_row=min(12,len(items))+1),titles_from_data=True)
            chart.set_categories(Reference(graph,min_col=1,min_row=2,max_row=min(12,len(items))+1));graph.add_chart(chart,anchor)
    trend=wb.create_sheet('연도별 원본 총계');append_row(trend,['연도','수입 예산','수입 결산','지출 예산','지출 결산'])
    for y,parsed in sorted(history.items()):append_row(trend,[y,*parsed['totals'].get('수입',(None,None)),*parsed['totals'].get('지출',(None,None))])
    if history:
        chart=LineChart();chart.title='연도별 자금 수입·지출 총계';chart.y_axis.title='원';chart.width=25;chart.height=12
        for c in (3,5):chart.add_data(Reference(trend,min_col=c,max_col=c,min_row=1,max_row=len(history)+1),titles_from_data=True)
        chart.set_categories(Reference(trend,min_col=1,min_row=2,max_row=len(history)+1));trend.add_chart(chart,'G2')
    for s in wb:format_sheet(s)
    summary.column_dimensions['B'].width=110
    return save_atomic(wb,target)
