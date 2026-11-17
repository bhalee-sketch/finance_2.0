"""Ledger screening from the user's tuition/non-tuition income recognition guidance."""
import re
from collections import Counter
from audit_balance_rules import CATALOG


def norm(value):return re.sub(r'[\s·ㆍ\-()]','',str(value or ''))

TUITION={'학부입학금','대학원입학금','학부수업료','대학원수업료','입학금','수업료'}
REVENUE={name for name,rule in CATALOG.items() if rule[3] in ('income','donation','grant')}
REVENUE|={'예금이자수입','교육부지원금','교육부기타지원금','교육부국가장학금','국가장학금지원금'}
REVENUE_GROUPS={'등록금수입','수강료수입','전입및기부수입','전입금수입','기부금수입','국고보조금수입','산학협력단및학교기업전입금','교육부대수입','교육외수입','수익재산수입'}
EXCEPTIONS={'잡수입','토지매각대','건물매각대','구축물매각대','기계기구매각대','집기비품매각대','차량운반구매각대','도서매각대','유물매각대','무형고정자산매각대'}
NON_REVENUE={'현금','예금','미수금','선수금','등록금선수금','임대보증금','임대보증금수입','예수금','일반예수금','미지급금','가수금','선급금'}


def scope(unit):
    value=norm(unit)
    # Existing statement/ledger convention: bare 교비 and 대학원 are tuition units.
    if value in ('교비','대학원','교비등록금','교비등록금회계'):return '등록금'
    if value.endswith(('비등록금','비등록금회계')):return '비등록금'
    if value in ('교비','대학원') or value.endswith(('등록금','등록금회계')):return '등록금'
    return None


def review_income(records):
    findings=[];counts=Counter()
    for record in records:
        unit=scope(record['회계단위']);name=norm(record['목']);parents={norm(record[k]) for k in ('관','항')}
        if record['차변']==0 and record['대변']==0:counts['금액 0 제외']+=1;continue
        if name in NON_REVENUE:continue
        # Determine income by account hierarchy, never by narrative words alone.
        tuition=name in TUITION or (bool(parents&{'등록금수입'}) and not (name=='단기수강료' or '수강료수입' in parents))
        exception=name in EXCEPTIONS or bool(parents&{'고정자산매각수입','유형고정자산매각수입','무형고정자산매각수입'})
        income=tuition or exception or name in REVENUE or bool(parents&REVENUE_GROUPS)
        if not income:continue
        counts['수입 거래']+=1
        state=reason=expected=''
        if unit is None:
            state='회계단위 확인';reason='등록금/비등록금 구분이 불명확하여 판정하지 않았습니다.';expected='확인 필요'
        elif tuition and unit=='비등록금':
            state='분류 의심';reason='등록금수입 계정이 비등록금회계에 기록되어 있습니다.';expected='등록금'
        elif not tuition and unit=='등록금':
            expected='비등록금 원칙'
            if exception:
                state='예외 확인';reason='고정자산 매각·잡수입 등 등록금회계에서 불가피하게 발생한 수입인지 발생 사유와 재원을 확인하세요.'
            else:
                state='분류 의심';reason='등록금 외 수입 계정이 등록금회계에 기록되어 있습니다. 비등록금회계 처리 원칙 및 예외 사유를 확인하세요.'
        if not state:counts['구분 일치']+=1;continue
        original_state=state
        description=norm(record['적요'])
        if record['차변']!=0 or record['대변']<0 or any(word in description for word in ('환불','취소','정정','대체','환입','반환')):
            state='정정·반환 확인';reason+=' 차변·음수 또는 정정/반환 표현이 있어 신규 수입으로 단정하지 말고 원거래와 함께 확인하세요.'
        item=dict(record=record,state=state,reason=reason,expected=expected,base_state=original_state)
        findings.append(item);counts[state]+=1
    return {'items':findings,'counts':counts,'total':len(records)}
