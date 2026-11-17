"""정기·보통예금 계좌 검색. 동일 이름도 계좌별로 보존한다."""
import re


def search_catalog(catalog,query):
    query=query.strip().casefold()
    if not query:return []
    exact=[k for k,v in catalog.items() if query in (v['name'].strip().casefold(),v['account'].strip().casefold())]
    if exact:return exact
    def search(term):
        return [k for k,v in catalog.items() if term in v['name'].casefold()
                or term in v['account'].casefold()
                or (term.isdigit() and term in re.sub(r'\D','',v['account']))]
    if re.fullmatch(r'\d{4}',query):
        padded=search('0'+query)
        if padded:return padded
    return search(query)


def resolve_catalog(catalog,options,query):
    if query in options:return options[query]
    found=search_catalog(catalog,query)
    if not found:raise ValueError('계좌명 또는 코드를 입력하고 일치하는 계좌를 확인하세요.')
    if len(found)>1:raise ValueError(f'{len(found)}개 계좌가 일치합니다. 입력칸 오른쪽 화살표를 눌러 계좌를 선택하세요.')
    return found[0]
