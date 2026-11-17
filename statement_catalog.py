"""파일명 기준 재무제표 회계연도 목록과 표시 정렬."""
from pathlib import Path
import re


def discover_years(folder):
    folder=Path(folder)
    if not folder.exists():return {}
    if not folder.is_dir():raise ValueError('finance statement는 폴더여야 합니다.')
    result={}
    candidates=list(folder.iterdir())
    for directory in sorted(folder.iterdir()):
        if directory.is_dir() and re.fullmatch(r'20\d{2}\s*회계연도',directory.name):
            candidates.extend(p for p in directory.iterdir() if p.stem.strip()==directory.name)
    for path in sorted(candidates):
        if not path.is_file() or path.name.startswith('~$') or path.suffix.lower() not in ('.xlsx','.xlsm'):continue
        match=re.fullmatch(r'(20\d{2})\s*회계연도',path.stem.strip())
        if not match:continue
        year=match.group(1)
        if year in result:raise ValueError(f'{year}회계연도 파일이 중복됩니다. 해당 연도 파일을 하나만 남겨 주세요: {result[year].name}, {path.name}')
        result[year]=path
    return dict(sorted(result.items(),reverse=True))


def discover_appendices(statement_path):
    """해당 재무제표 옆의 부속명세서만 연결한다. 중복은 임의 선택하지 않는다."""
    statement_path=Path(statement_path)
    result={}
    year=re.match(r'20\d{2}',statement_path.stem).group()
    for kind in ('재무상태표','운영계산서'):
        matches=[p for p in sorted(statement_path.parent.iterdir())
                 if p.is_file() and not p.name.startswith('~$')
                 and p.suffix.lower() in ('.xlsx','.xlsm','.xls')
                 and year in p.stem and kind in p.stem and '부속명세서' in p.stem]
        if len(matches)>1:raise ValueError(f'{year} {kind} 부속명세서가 중복됩니다. 파일을 하나만 남겨 주세요.')
        result[kind]=matches[0] if matches else None
    return result


def column_anchor(type_key,index):
    # 시산표의 코드·과목은 식별용 텍스트다. 나머지는 금액 열.
    if type_key=='trial':return 'center' if index in (2,3) else 'e'
    return 'w' if index==0 else 'e'


def amount_text(value):
    """불필요한 .0 없이 천 단위 구분. 유효한 소수 금액은 유지한다."""
    from decimal import Decimal,InvalidOperation
    if value is None:return ''
    try:
        number=Decimal(str(value).replace(',',''))
        if not number.is_finite():return ''
    except InvalidOperation:return str(value)
    result=format(number,',f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def subject_display(row):
    """과목명에 추가 문구 없이 계층 들여쓰기만 적용한다."""
    return '    '*row.get('indent',0)+str(row['values'][0])
