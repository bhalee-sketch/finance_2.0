"""settings/accountsforfinancecode.xlsx의 회계단위별 계좌 목록."""
from pathlib import Path
from verifier import excel_rows


def load_finance_accounts(path):
    path=Path(path)
    if not path.is_file():
        raise ValueError(f'계좌 목록 파일을 찾을 수 없습니다.\n{path}')
    rows=iter(excel_rows(path,1));header=None
    for index,row in enumerate(rows):
        labels=[str(v or '').strip() for v in row]
        if {'회계단위','계좌명'}.issubset(labels):header=labels;break
        if index>=49:break
    if header is None:raise ValueError('계좌 목록에 회계단위, 계좌명 열이 필요합니다.')
    unit_col=header.index('회계단위');account_col=header.index('계좌명');catalog={}
    for row in rows:
        unit=str(row[unit_col] or '').strip() if unit_col<len(row) else ''
        account=str(row[account_col] or '').strip() if account_col<len(row) else ''
        if not unit and not account:continue
        if not unit or not account:raise ValueError('계좌 목록에 회계단위 또는 계좌명이 빈 행이 있습니다.')
        accounts=catalog.setdefault(unit,[])
        if account not in accounts:accounts.append(account)
    if not catalog:raise ValueError('계좌 목록이 비어 있습니다.')
    return catalog
