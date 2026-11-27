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
RULE_VERSION='2023.12-review-v6'
RULES={
 '건축물관리비':('BUILDING','362~363, 373','일상적인 건물 유지·보수와 경제적 가치·내용연수를 늘리는 자본적 지출 또는 자산 취득을 구분합니다.','공사계약서·견적/내역서·준공자료·자산대장·자본적 지출 내부 기준'),
 '회의비':('MEETING','371','회의 지출은 회의 사실을 근거로 처리하며 적격증빙과 회의록 등이 필요합니다.','회의록·참석자·지출결의서·영수증'),
 '차량유지비':('VEHICLE','366','차량 유류·수리비와 차량 보험료는 계정 구분이 필요합니다.','보험증권·차량 내역·지출결의서'),
 '복리후생비':('WELFARE','367~368, 373','교직원 복리후생 목적과 지출 대상을 확인하고 학생지원 등 다른 목적과 구분합니다.','수혜자 명단·행사 목적·지출결의서'),
 '여비교통비':('TRAVEL','365~366','교직원 출장 목적과 여비규정에 따른 교통·숙박·일비 등의 지출인지 확인합니다.','출장신청서·출장복명서·여비 산출내역·영수증'),
 '소모품비':('SUPPLIES','366, 373','일반 사무 소모품과 내용연수 1년 이상 집기비품 취득은 구분하여 검토합니다.','구매명세·물품규격·자산대장·내부 자산관리 기준'),
 '업무추진비':('BUSINESS','368, 373','업무 관련성 증빙과 교직원/외부인 지출 대상 구분을 확인합니다.','업무 목적·참석자/수혜자·지출결의서·영수증'),
}
from audit_account_rules import ACCOUNTS
from audit_balance_rules import CATALOG,CREDIT_ALLOWED
for _name,(_pages,_definition,_evidence,_clues) in ACCOUNTS.items():
    RULES[_name]=('ACCOUNT_'+_name,_pages,_definition,_evidence)

for _name,(_pages,_definition,_evidence,_kind) in CATALOG.items():
    RULES[_name]=('CATALOG_'+_name,_pages,_definition,_evidence)

CAPITAL_REVIEW='자본적 지출 의심'
REVIEW_VIEWS=('분류 의심',CAPITAL_REVIEW,'적요 불충분','전체')
AUDIT_HEADERS=['확인 상태','년도','회계단위','관','항','목','회계일자','전표번호','차변','대변','거래선명','적요','걸린 표현','검토할 과목','확인 사유','근거 페이지','원본 파일','원본 행']

AUDIT_SOURCE_FIELDS=('년도','원본 파일','원본 행')
AUDIT_EXPORT_INDICES=tuple(i for i,h in enumerate(AUDIT_HEADERS) if h not in ('검토할 과목','근거 페이지'))
AUDIT_VISIBLE_INDICES=tuple(i for i in AUDIT_EXPORT_INDICES
                           if AUDIT_HEADERS[i] not in (*AUDIT_SOURCE_FIELDS,'확인 상태','걸린 표현'))
AUDIT_VISIBLE_HEADERS=[AUDIT_HEADERS[i] for i in AUDIT_VISIBLE_INDICES]


def normalized(value):return re.sub(r'[\s·ㆍ]','',str(value or ''))


def rule_for(subject):
    name=normalized(subject)
    name={'리스및임차료':'리스임차료','각종세금및공과금':'각종세금공과금','예금이자수입':'예금이자','교육부지원금':'교육부','임대보증금반환':'임대보증금환급'}.get(name,name)
    if name in ('기관장업무추진비','상임이사업무추진비','기타업무추진비'):name='업무추진비'
    return name,RULES.get(name)


# Each candidate needs a specific expression in the posting's own narrative.
# The optional third field requires purchase language for ambiguous asset names.
CONFLICT_RULES = {
    '차량유지비': [('자동차보험료 차량보험료 자동차보험 차량보험 보험료', '보험료')],
    '지급수수료': [('법률자문 회계자문 노무자문 회계감사 감정평가 세무용역', '일반용역비')],
    '여비교통비': [('복사용지 토너 사무용품구입', '소모품비')],
    '홍보비': [('입시 신입생모집 입학홍보 수시모집 정시모집', '입시경비')],
    '통신비': [('휴대폰구입 전화기구입 장비구입', '집기비품매입비·기계기구매입비')],
    '실험실습비': [('기자재구입 장비구입 기계구입', '기계기구매입비')],
    '장비관리비': [('신규구입 신규취득 자산취득', '기계기구매입비·집기비품매입비')],
    '건축물관리비': [('증축 신축 건물취득 건축물취득', '건물매입비·건설중인자산'),
                ('청소용역 청소위탁', '시설용역비'), ('청소용품 세제구입', '소모품비')],
    '소모품비': [('노트북 컴퓨터 냉장고 에어컨 냉난방기 책상', '집기비품매입비·기계기구매입비', '구입 구매 취득')],
    '복리후생비': [('학생장학', '교내장학금·교외장학금'), ('학생지원', '학생지원비'),
              ('논문심사료', '논문심사료'), ('복사용지 토너', '소모품비')],
    '업무추진비': [('조의 축의 경조 명절선물', '복리후생비', '교직원 직원 교원')],
    '교육훈련비': [('학생대상', '학생지원비')],
    '회의비': [('회식', '복리후생비')],
    '지급이자': [('원금상환', '차입금 상환 과목')],
    '단기수강료': [('계절학기', '학부수업료·대학원수업료')],
    '대여료및사용료': [('보증금', '임대보증금수입')],
    '임대료수입': [('보증금', '임대보증금수입')],
    '일반기부금': [('용도지정 지정기부', '지정기부금'), ('연구목적', '연구기부금')],
    '조교인건비': [('장학조교', '교내장학금·교외장학금')],
    '도서': [('구독료 부서간행물', '소모품비')],
    '도서구입비': [('구독료 부서간행물', '소모품비')],
    '건물매입비': [('유지보수 정기점검 단순수리', '건축물관리비')],
    '기계기구매입비': [('유지보수 정기점검 단순수리', '장비관리비')],
    '집기비품매입비': [('유지보수 정기점검 단순수리', '장비관리비')],
    '자산전입금': [('토지 건축물 건물', '설립자기본금·기타기본금')],
}
for _name, (_, _, _, _kind) in CATALOG.items():
    if _kind == 'repayment':
        CONFLICT_RULES[_name] = [('이자', '지급이자')]

# These contexts weaken a keyword match enough to leave it out of the default list.
EXCLUDE_CONTEXT = {
    '회의비': ('회의', '간담회', '협의회'),
    '소모품비': ('부품', '소모품', '수리', '토너', '충전기', '케이블', '마우스', '배터리', '가방', '책상조명', '책상용', '노트북용', '컴퓨터용', '거치대'),
    '교육훈련비': ('교원', '직원'),
}


# Match concrete changes to the asset. Ordinary repairs or a large payment
# alone say nothing about whether the asset's future benefit has increased.
FACILITY_THRESHOLD = 10_000_000
FACILITY_BASIS = '일반기업회계기준 제10장 문단 10.14 · 법인세법 시행령 제31조 제2항 · 시행규칙 제17조'
FACILITY_CRITERIA = '시설관리비 항의 건별 차변 1,000만 원 이상. 적요에서 용도변경·개량·증설·내용연수 연장 등 단서를 확인합니다.'
FACILITY_CLUE = re.compile(
    r'용도(?:를)?변경|내용연수(?:를)?연장|(?:생산|처리|수용)능력(?:을)?(?:증대|확대|향상)|'
    r'(?:성능|품질|기능)(?:을|를)?(?:향상|개선)|(?:원가|에너지비용)(?:를|을)?절감(?:설비|공사)|'
    r'(?:증축|개축|증설|신축|개량|확장)(?!동|관|건물|건축물|부지|현장)(?:공사|사업|설계|설치)?|'
    r'리모델링|(?:승강기|엘리베이터|(?:냉난방|냉방|난방)(?:장치|기|설비)|피난시설|비상계단|창고|닥트|덕트)(?:를|을|의)?(?:신규|추가)?(?:설치|신설)|'
    r'(?:시설|설비|강의실|실험실)(?:을|를)?(?:신설|신규구축)|'
    r'(?:멸실|사용불능|전파|전소)(?:된)?(?:건축물|건물|기계|설비)(?:의)?(?:복구|재건)'
)


FACILITY_IMPROVEMENT = re.compile(r'(?:환경개선|인테리어|도로개선)공사')
ROUTINE_REPAIR = re.compile(r'도장|도색|도배|방수|누수|보수|수리|점검|유지|교체|청소|정비')


def inspect_record(record):
    name, rule = rule_for(record['목'])
    memo = str(record['적요'] or '')
    description = normalized(memo)
    result = dict(record=record, state='규칙 미등록', reason='등록된 과목 규칙이 없습니다.',
                  clue='', candidate='', reference='')
    facility = (record['차변'] >= FACILITY_THRESHOLD and record['대변'] == 0
                and normalized(record.get('항')) == '시설관리비')
    if rule:
        section = '부록' if name in CATALOG else '본문'
        result['reference'] = f'{DOCUMENT} · {section} {rule[1]}쪽'
    elif not facility:
        return result
    if not description or description in ('지급','비용지급','비용','대금','대금지급','집행','구입','수입','입금',
                                         name,name+'지급',name+'집행'):
        result.update(state='적요 불충분', reason='거래의 목적이나 대상이 적요에 드러나지 않습니다.')
        return result

    if (any(term in description for term in ('취소','환입','반납','정정','환불','아님','아닌','제외'))
            or (name not in CATALOG and ('대체' in description or record['차변'] < 0 or record['대변'] < 0))
            or (name not in CREDIT_ALLOWED and record['대변'] != 0)):
        result.update(state='원거래 확인', reason='취소·정정 표현 또는 차대변 방향 등으로 원거래와 함께 검토할 항목입니다.')
        return result

    if facility:
        match = FACILITY_CLUE.search(description)
        if not match and not ROUTINE_REPAIR.search(description):
            match = FACILITY_IMPROVEMENT.search(description)
        if match:
            excerpt = re.search(r'[\s·ㆍ]*'.join(map(re.escape, match.group())), memo).group()
            reference = ' · '.join(filter(None, (result['reference'], FACILITY_BASIS)))
            result.update(state='분류 의심', candidate=CAPITAL_REVIEW, clue=excerpt, reference=reference,
                          reason=f'시설관리비 1,000만 원 이상 거래로 적요에 “{excerpt}” 표현이 있어 자본적 지출 가능성을 검토합니다.')
            return result
    if rule is None:
        return result

    if not any(term in description for term in EXCLUDE_CONTEXT.get(name, ())):
        for words, candidate, *qualifiers in CONFLICT_RULES.get(name, ()):
            clue = next((word for word in words.split() if word in description), None)
            if not clue:
                continue
            if clue == '회식' and not re.search(r'회식(?![사대])', memo):
                continue
            clues = [clue]
            if qualifiers:
                qualifier = next((word for word in qualifiers[0].split() if word in description), None)
                if not qualifier:
                    continue
                clues.append(qualifier)
            # Keep the original spacing and punctuation in the words shown to the reviewer.
            excerpts = [re.search(r'[\s·ㆍ]*'.join(map(re.escape, word)), memo).group() for word in clues]
            result.update(state='분류 의심', clue=' · '.join(excerpts), candidate=candidate,
                          reason=f'적요에 {candidate} 관련 표현이 있습니다.')
            return result

    result.update(state='탐지 사항 없음', reason='적요에서 다른 계정과목을 검토할 단서를 찾지 못했습니다.')
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
            item['clue'],item['candidate'],item['reason'],item['reference'],r.get('_source_file',''),r.get('_source_row','')]


def export_review(data,items,filters,target):
    wb=Workbook();sheet=wb.active;sheet.title='계정과목 검토';headers=[AUDIT_HEADERS[i] for i in AUDIT_EXPORT_INDICES]
    append_row(sheet,headers)
    for item in items:
        values=review_values(item)
        append_row(sheet,[values[i] for i in AUDIT_EXPORT_INDICES])
        if item['state'] == '분류 의심':
            for index in range(1,len(headers)+1):sheet.cell(sheet._current_row,index).fill=PatternFill('solid',fgColor='FFF2CC')
    criteria=wb.create_sheet('점검 기준');append_row(criteria,['항목','내용'])
    for row in [('자료',DOCUMENT),('규칙 버전',RULE_VERSION),(CAPITAL_REVIEW,FACILITY_CRITERIA),('점검 범위',f'등록된 {len(RULES)}개 과목군의 적요 표현을 이용한 예비 점검. 문서에 없는 기준은 임의 적용하지 않습니다.'),
                ('판정 한계','탐지 사항 없음은 적정 판정이 아닙니다. 규칙 미등록은 미점검이며, 판정은 적요에 적힌 표현에 한정합니다.'),
                ('과목 순서','최신 재무제표 순서 → 이전 연도 추가 과목 → 원장에만 있는 과목. 금액순 정렬 없음.')]:append_row(criteria,row)
    for k,v in filters.items():append_row(criteria,[k,v or '전체'])
    for path in data['sources']:append_row(criteria,['원본',path])
    for issue in data['issues']:append_row(criteria,['자료 확인 필요',issue])
    for account, rules in CONFLICT_RULES.items():
        for words, candidate, *qualifiers in rules:
            condition = f' (함께 기재: {qualifiers[0]})' if qualifiers else ''
            append_row(criteria,[account, f'{words}{condition} → {candidate}'])
    for state,count in Counter(x['state'] for x in items).items():append_row(criteria,[state,count])
    for s in wb:format_sheet(s)
    for cell in sheet[1]:
        if cell.value in AUDIT_SOURCE_FIELDS:sheet.column_dimensions[cell.column_letter].hidden=True
    for row in sheet.iter_rows(min_row=2):
        for c in row:c.alignment=Alignment(horizontal='right' if headers[c.column-1] in ('차변','대변','원본 행') else 'left',vertical='top',wrap_text=True)
        line_count=max((max(1,(sum(2 if ord(ch)>127 else 1 for ch in str(c.value or ''))+63)//64) for c in row if headers[c.column-1] not in AUDIT_SOURCE_FIELDS),default=1)
        sheet.row_dimensions[row[0].row].height=max(36,min(240,line_count*15+8))
    criteria.column_dimensions['B'].width=110
    return save_atomic(wb,target)


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
