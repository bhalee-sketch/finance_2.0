"""사용자가 제공한 2023.12 특례규칙 해설서 기반의 제한된 적요 점검.
외부 서비스 전송 없이 실행한다. 결과는 검토 단서이며 적정성 확정 판정이 아니다.
"""
from collections import Counter
from pathlib import Path
import re
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import PatternFill, Alignment
from finance_data import (load_ledger,discover_ledger_years,LEDGER_COLUMNS,
                          append_row,format_sheet,save_atomic)
from statement_catalog import discover_years
from statement_loader import load_statement_record_from_path
from statement_analysis import parse_fund

DOCUMENT='사학기관 재무회계 규칙에 대한 특례규칙 해설서(2023.12)'
RULE_VERSION='2023.12-review-v4'
RULES={
 '건축물관리비':('BUILDING','362~363, 373','일상적인 건물 유지·보수와 경제적 가치·내용연수를 늘리는 자본적 지출 또는 자산 취득을 구분합니다.','공사계약서·견적/내역서·준공자료·자산대장·자본적 지출 내부 기준'),
 '회의비':('MEETING','371','회의 지출은 회의 사실을 근거로 처리하며 적격증빙과 회의록 등이 필요합니다.','회의록·참석자·지출결의서·영수증'),
 '차량유지비':('VEHICLE','366','차량 유류·수리비와 차량 보험료는 계정 구분이 필요합니다.','보험증권·차량 내역·지출결의서'),
 '복리후생비':('WELFARE','367~368, 373','교직원 복리후생 목적과 지출 대상을 확인하고 학생지원 등 다른 목적과 구분합니다.','수혜자 명단·행사 목적·지출결의서'),
 '여비교통비':('TRAVEL','365~366','교직원 출장 목적과 여비규정에 따른 교통·숙박·일비 등의 지출인지 확인합니다.','출장신청서·출장복명서·여비 산출내역·영수증'),
 '소모품비':('SUPPLIES','366, 373','일반 사무 소모품과 내용연수 1년 이상 집기비품 취득은 구분하여 검토합니다.','구매명세·물품규격·자산대장·내부 자산관리 기준'),
 '업무추진비':('BUSINESS','368, 373','업무 관련성 증빙과 교직원/외부인 지출 대상 구분을 확인합니다.','업무 목적·참석자/수혜자·지출결의서·영수증'),
}
from audit_account_rules import ACCOUNTS,review_extra
from audit_balance_rules import CATALOG,CREDIT_ALLOWED,review_catalog
for _name,(_pages,_definition,_evidence,_clues) in ACCOUNTS.items():
    RULES[_name]=('ACCOUNT_'+_name,_pages,_definition,_evidence)

for _name,(_pages,_definition,_evidence,_kind) in CATALOG.items():
    RULES[_name]=('CATALOG_'+_name,_pages,_definition,_evidence)

CHECK_STATES={'분류 의심','증빙 확인 필요','정보 부족'}
AUDIT_HEADERS=['확인 상태','년도','회계단위','관','항','목','회계일자','전표번호','차변','대변','거래선명','적요','확인 사유','근거 페이지','확인할 증빙','원본 파일','원본 행']


def normalized(value):return re.sub(r'[\s·ㆍ]','',str(value or ''))


def rule_for(subject):
    name=normalized(subject)
    name={'리스및임차료':'리스임차료','각종세금및공과금':'각종세금공과금','예금이자수입':'예금이자','교육부지원금':'교육부','임대보증금반환':'임대보증금환급'}.get(name,name)
    if name in ('기관장업무추진비','상임이사업무추진비','기타업무추진비'):name='업무추진비'
    return name,RULES.get(name)


def inspect_record(record):
    name,rule=rule_for(record['목']);description=normalized(record['적요'])
    result={'record':record,'state':'규칙 미등록','reason':'이 목의 적요 점검 규칙은 아직 등록되지 않았습니다.',
            'reference':'','evidence':'','rule_id':''}
    if rule is None:return result
    identifier,pages,explanation,evidence=rule
    result.update(state='탐지 사항 없음',reason='등록된 제한적 규칙에서 의심 표현이 탐지되지 않았습니다. 적정성 확정 판정은 아닙니다.',
                  reference=f'{DOCUMENT} · 본문 {pages}쪽',evidence=evidence,rule_id=identifier)
    def flag(state,reason):result.update(state=state,reason=reason+' '+explanation);return result
    if not description or description in ('지급','비용지급','비용','대금지급',name,name+'지급',name+'집행'):
        return flag('정보 부족','적요만으로 지출 목적·대상을 구분하기 어렵습니다.')
    reversal_terms=('취소','환입','반납','정정','환불','아님','아닌','제외')
    if any(t in description for t in reversal_terms) or (name not in CATALOG and '대체' in description) or (name not in CATALOG and (record['차변']<0 or record['대변']<0)) or (name not in CREDIT_ALLOWED and record['대변']!=0):
        return flag('정보 부족','취소·환입·정정·대체 또는 대변 거래 가능성이 있어 원거래 확인 후 분류를 판단해야 합니다.')
    if name in CATALOG:
        result['reference']=f'{DOCUMENT} · 부록 {pages}쪽'
        state,reason=review_catalog(name,description)
        result.update(state=state,reason=reason)
        return result
    if name in ACCOUNTS:
        state,reason=review_extra(name,description)
        return flag(state,reason)
    if name=='건축물관리비':
        if any(t in description for t in ('증축','신축','건물취득','건축물취득','내용연수연장','자산취득')):
            return flag('분류 의심','건물 가치·내용연수 증가 또는 취득을 나타내는 표현이 있습니다. 자산 계상 대상인지 공사 실질을 확인하세요.')
        if '청소' in description:
            result['reference']=f'{DOCUMENT} · 본문 362~364쪽 · 부록 470쪽'
            result['evidence']='청소 계약서·작업내역·용품 또는 장비 구매/수리명세'
            if any(t in description for t in ('용품','세제','청소기','장비','수리')):
                return flag('증빙 확인 필요','청소 관련 물품·장비 표현이 있습니다. 청소용역인지 소모품 구입 또는 장비 수리·취득인지 구분하세요.')
            result.update(state='증빙 확인 필요',reason='건물 청소라는 유지 활동이 확인됩니다. 해설서의 시설용역비(청소·경비 등)에 해당하는 비용인지 계약·작업내역을 확인하세요.')
            return result
        if any(t in description for t in ('리모델링','대수선','설치','인수','교체','냉난방기','에어컨','승강기')):
            return flag('증빙 확인 필요','공사·설비 지출의 성격이 적요만으로 명확하지 않습니다. 단순 유지보수인지 자산 취득·성능 개선인지 확인하세요.')
        if not any(t in description for t in ('보수','수리','방수','도장','유지','관리','파손')):
            return flag('정보 부족','건물 유지·보수 목적과 공사 범위를 적요만으로 확인하기 어렵습니다.')
    if name=='회의비':
        if '회식' in description and '회의' not in description:return flag('분류 의심','회의비 적요에 회식이 기재되어 있어 회의 목적의 지출인지 확인이 필요합니다.')
        if any(t in description for t in ('회의','간담회','협의회')):return flag('증빙 확인 필요','적요에 회의 관련 표현이 있으나 실제 회의 개최 여부와 참석자는 증빙으로 확인해야 합니다.')
        return flag('정보 부족','회의 개최 사실·목적이 적요에서 명확하지 않습니다.')
    if name=='차량유지비' and any(t in description for t in ('보험료','자동차보험','차량보험')):
        return flag('분류 의심','차량 보험 관련 지출로 보입니다. 보험료 계정 해당 여부를 확인하세요.')
    if name=='복리후생비':
        if any(t in description for t in ('학생지원','학생장학','논문심사료','복사용지','토너')):
            return flag('분류 의심','교직원 복리후생과 다른 목적의 표현이 있습니다. 수혜자와 구입 목적을 확인하세요.')
        if any(t in description for t in ('외부인','외빈','거래처','내빈')):
            return flag('증빙 확인 필요','외부 대상 지출 표현이 있습니다. 수혜자와 업무추진비 해당 여부를 확인하세요.')
        if any(t in description for t in ('식대','식사','선물','경조','조의','축의')) and not any(t in description for t in ('교직원','직원','교원')):
            return flag('정보 부족','식사·선물·경조사 등의 수혜자가 적요에 명확하지 않습니다.')
    if name=='여비교통비' and any(t in description for t in ('복사용지','토너','사무용품구입')):
        return flag('분류 의심','출장 여비보다 물품 구입으로 보이는 표현이 있어 지출 목적을 확인해야 합니다.')
    if name=='소모품비' and any(t in description for t in ('노트북','컴퓨터','냉장고','에어컨','냉난방기','책상')):
        return flag('증빙 확인 필요','내구성 물품 관련 표현이 있습니다. 소모품·부품·수리인지 자산 취득인지 규격과 사용기간을 확인하세요.')
    if name=='업무추진비':
        if any(t in description for t in ('교직원','직원','교원')) and any(t in description for t in ('조의','축의','경조','명절선물')):
            return flag('분류 의심','내부 교직원 경조·선물 표현이 있어 복리후생 목적 여부를 확인해야 합니다.')
        return flag('증빙 확인 필요','업무 관련성을 확인할 목적·참석자·수혜자 증빙이 필요합니다.')
    return result


def load_statement_history(settings,*,paths=None,reader=None):
    if paths is None:paths=discover_years(Path(settings)/'finance statement')
    history={};issues=[]
    for year,path in paths.items():
        history[year]={}
        try:record=load_statement_record_from_path(path) if reader is None else reader(year,path)
        except Exception as e:issues.append(f'{path.name}: {e}');continue
        scopes={}
        for scope in ('전체','등록금','비등록금'):
            try:scopes[scope]=parse_fund(record,scope)
            except ValueError as e:
                if scope=='전체':issues.append(f'{path.name}: {e}')
        history[year]=scopes
    if not paths:issues.append('재무제표 없음: 과목은 원장 첫 등장 순서로 표시하며 결산 추이는 제공되지 않습니다.')
    return history,issues,paths


class AccountOrder:
    """최신 재무제표 위→아래 순서. 이전 연도 및 원장에만 있는 항목은 해당 부모 끝에 추가."""
    def __init__(self,history=None,records=()):
        self.ranks={};self.labels={};self.statement_paths=set()
        for year in sorted(history or {},reverse=True):
            for scope in ('전체','등록금','비등록금'):
                for item in history[year].get(scope,{}).get('items',{}).values():
                    self.add(item['path'],True)
        for record in records:self.add(tuple(record[k] for k in ('관','항','목')))
    def add(self,path,statement=False):
        for size in range(1,len(path)+1):
            raw=tuple(path[:size]);key=tuple(normalized(x) for x in raw)
            if key not in self.ranks:self.ranks[key]=len(self.ranks);self.labels[key]=raw[-1]
            if statement:self.statement_paths.add(key)
    def key(self,record):
        path=tuple(normalized(record[k]) for k in ('관','항','목'))
        return tuple(self.ranks.get(path[:i],10**9) for i in (1,2,3))
    def choices(self,records,column):
        size=('관','항','목').index(column)+1;found={}
        for r in records:
            path=tuple(normalized(r[k]) for k in ('관','항','목')[:size]);value=self.labels.get(path,r[column])
            if value and normalized(value) not in found:found[normalized(value)]=(self.ranks.get(path,10**9),value)
        return [value for _,value in sorted(found.values(),key=lambda pair:pair[0])]


def matches(record,filters):
    return all(not value or value=='전체' or normalized(record.get(key,''))==normalized(value) for key,value in filters.items())


def _load_sources(settings,year=None):
    settings=Path(settings);records=[];issues=[];loaded_years=[];paths=discover_ledger_years(settings/'lodges')
    available_years=list(paths)
    if year is not None:paths={y:p for y,p in paths.items() if y==str(year)}
    for year,path in paths.items():
        try:
            data=load_ledger(path,with_provenance=True)
            loaded_years.append(year)
            for r in data:r['_file_year']=year
            records.extend(data)
        except Exception as e:issues.append(f'{path.name}: {e}')
    try:history,notes,statement_paths=load_statement_history(settings)
    except Exception as e:history={};notes=[f'재무제표 자료 확인 필요: {e}'];statement_paths={}
    issues.extend(notes)
    if not paths:issues.append('settings/lodges에 연도별 원장 파일이 없습니다.')
    order=AccountOrder(history,records);records.sort(key=order.key)
    return {'reviews':[inspect_record(r) for r in records],'history':history,'order':order,
            'issues':issues,'ledger_years':available_years,'sources':[str(p) for p in [*paths.values(),*statement_paths.values()]]}


_REVIEW_CACHE={}


def load_sources(settings,year=None):
    # 원장 및 재무제표 내용이 동일하면 분류·정렬·점검을 재실행하지 않는다.
    from ledger_cache import fingerprint
    settings=Path(settings)
    ledger_paths=discover_ledger_years(settings/'lodges')
    selected=[p for y,p in ledger_paths.items() if year is None or y==str(year)]
    statements=discover_years(settings/'finance statement')
    key=(str(settings.resolve()),str(year),tuple((y,str(p)) for y,p in ledger_paths.items()),RULE_VERSION,tuple((str(p),fingerprint(p)) for p in selected+list(statements.values())))
    cached=_REVIEW_CACHE.get(key)
    if cached is not None:return cached
    result=_load_sources(settings,year);_REVIEW_CACHE.clear();_REVIEW_CACHE[key]=result
    return result


def scope_for(unit):
    value=normalized(unit).replace('교비','').replace('-','')
    return {'전체':'전체','등록금':'등록금','비등록금':'비등록금'}.get(value)


def trend_values(history,filters):
    scope=scope_for(filters.get('회계단위','전체'))
    if scope is None:return [],'선택 단위에 대응하는 재무제표가 없어 추이를 표시하지 않습니다.'
    path=tuple(normalized(filters.get(k,'')) for k in ('관','항','목') if filters.get(k,'전체') not in ('','전체'))
    result=[]
    for year in sorted(history):
        parsed=history[year].get(scope);values=[]
        for section in ('수입','지출'):
            if parsed is None:value=None
            elif not path:value=parsed['totals'].get(section,(None,None))[1]
            else:
                found=[item['actual'] for item in parsed['items'].values() if item['section']==section and tuple(normalized(v) for v in item['path'])==path]
                value=found[0] if len(found)==1 else None
            values.append(value)
        result.append([year,*values])
    return result,'자금계산서 원본 결산액 · 수입/지출 별도 · 과목이 없거나 값이 없으면 공란'


def review_values(item):
    r=item['record']
    return [item['state'],*[r[k] for k in ('년도','회계단위','관','항','목','회계일자','전표번호','차변','대변','거래선명','적요')],
            item['reason'],item['reference'],item['evidence'],r.get('_source_file',''),r.get('_source_row','')]


def export_review(data,items,filters,target):
    wb=Workbook();sheet=wb.active;sheet.title='계정과목 검토';append_row(sheet,AUDIT_HEADERS)
    for item in items:
        append_row(sheet,review_values(item))
        if item['state'] in CHECK_STATES:
            for index in range(1,len(AUDIT_HEADERS)+1):sheet.cell(sheet._current_row,index).fill=PatternFill('solid',fgColor='FFF2CC')
    criteria=wb.create_sheet('점검 기준');append_row(criteria,['항목','내용'])
    for row in [('자료',DOCUMENT),('규칙 버전',RULE_VERSION),('점검 범위',f'등록된 {len(RULES)}개 과목군의 적요 표현을 이용한 예비 점검. 문서에 없는 기준은 임의 적용하지 않습니다.'),
                ('판정 한계','탐지 사항 없음은 적정 판정이 아닙니다. 규칙 미등록은 미점검이며, 증빙과 내부 규정·해당 연도 규정 확인이 필요합니다.'),
                ('과목 순서','최신 재무제표 순서 → 이전 연도 추가 과목 → 원장에만 있는 과목. 금액순 정렬 없음.')]:append_row(criteria,row)
    for k,v in filters.items():append_row(criteria,[k,v or '전체'])
    for path in data['sources']:append_row(criteria,['원본',path])
    for issue in data['issues']:append_row(criteria,['자료 확인 필요',issue])
    for account,(identifier,pages,reason,evidence) in RULES.items():append_row(criteria,[f'{identifier} · {account}',f'본문 {pages}쪽 | {reason} | 확인: {evidence}'])
    for state,count in Counter(x['state'] for x in items).items():append_row(criteria,[state,count])
    for s in wb:format_sheet(s)
    for column in ('B','P','Q'):sheet.column_dimensions[column].hidden=True
    for row in sheet.iter_rows(min_row=2):
        for c in row:c.alignment=Alignment(horizontal='right' if c.column in (9,10,17) else 'left',vertical='top',wrap_text=True)
        line_count=max((max(1,(sum(2 if ord(ch)>127 else 1 for ch in str(c.value or ''))+63)//64) for c in row if c.column not in (2,16,17)),default=1)
        sheet.row_dimensions[row[0].row].height=max(36,min(240,line_count*15+8))
    criteria.column_dimensions['B'].width=110
    return save_atomic(wb,target)


AUDIT_VISIBLE_INDICES=tuple(i for i,h in enumerate(AUDIT_HEADERS) if h not in ('년도','원본 파일','원본 행'))
AUDIT_VISIBLE_HEADERS=[AUDIT_HEADERS[i] for i in AUDIT_VISIBLE_INDICES]


def review_years(data):
    return sorted(set(data.get('ledger_years',[]))|{str(x['record'].get('_file_year',x['record']['년도'])) for x in data['reviews']},reverse=True)


def select_reviews(data,year,filters,query=''):
    query=query.strip().casefold()
    year=str(year)
    conditions=[(key,normalized(value)) for key,value in filters.items() if value and value!='전체']
    return [item for item in data['reviews'] if str((record:=item['record']).get('_file_year',record['년도']))==year
            and all(normalized(record.get(key,''))==value for key,value in conditions)
            and (not query or any(query in str(record[key]).casefold() for key in ('적요','거래선명','전표번호')))]


def visible_review_values(item):
    values=review_values(item)
    return [values[i] for i in AUDIT_VISIBLE_INDICES]


def export_trends(history,filters,target,sources=(),issues=()):
    wb=Workbook();sheet=wb.active;sheet.title='연도별 추이'
    values,note=trend_values(history,filters);append_row(sheet,['년도','수입 결산','지출 결산'])
    for row in values:append_row(sheet,row)
    if values:
        chart=LineChart();chart.title='관·항·목 선택 기준 결산 추이';chart.y_axis.title='원';chart.display_blanks='gap';chart.width=25
        chart.add_data(Reference(sheet,min_col=2,max_col=3,min_row=1,max_row=len(values)+1),titles_from_data=True)
        chart.set_categories(Reference(sheet,min_col=1,min_row=2,max_row=len(values)+1));sheet.add_chart(chart,'E2')
    criteria=wb.create_sheet('분석 기준');append_row(criteria,['항목','내용']);append_row(criteria,['기준',note])
    for k,v in filters.items():append_row(criteria,[k,v])
    for path in sources:append_row(criteria,['원본',str(path)])
    for issue in issues:append_row(criteria,['자료 확인 필요',issue])
    for s in wb:format_sheet(s)
    criteria.column_dimensions['B'].width=100
    return save_atomic(wb,target)
