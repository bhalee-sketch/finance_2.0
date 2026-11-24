from openpyxl import Workbook, load_workbook
import pytest

from cash_account_filter import filter_cash_accounts


def test_extract_keeps_full_rows_in_order_and_uses_the_correct_year(tmp_path):
    source, target = tmp_path / '원장.xlsx', tmp_path / '결과.xlsx'
    header = ['년도', '적요', '관', '항', '목', '계정코드', '차변', '대변']
    interest = ('교육외수입', '예금이자수입', '예금이자수입')
    purchase = ('고정자산', '유형고정자산', '기계기구매입비')
    history = {'2024': {'datasets': {('전체', '합계'): {'items': {
        1: {'section': '수입', 'path': interest}}}}},
               '2025': {'datasets': {('전체', '합계'): {'items': {
        1: {'section': '수입', 'path': interest}, 2: {'section': '지출', 'path': purchase}}}}}}
    keep = [2024, '=문자', *interest[:2], '예금이자', '0001', 0, 1500]
    equipment = [2025, '매입', *purchase[:2], '기계기구', '0002', 2000, 0]
    wb = Workbook()
    ws = wb.active
    for row in (header, keep, [2024, *equipment[1:]], equipment,
                [2025, *equipment[1:-2], 0, 300], [2025, '', '유동자산', '유동자금', '예금', '123', 1500, 0]):
        ws.append(row)
    ws['B2'].data_type = 's'
    wb.save(source)
    assert filter_cash_accounts(source, target, history) == (target, 5, 2)
    output = load_workbook(target, read_only=True)
    try:
        assert list(output.active.values) == list(map(tuple, [header, keep, equipment]))
    finally:
        output.close()
    old = target.read_bytes()
    ws.append(['연도오류', *equipment[1:]])
    wb.save(source)
    with pytest.raises(ValueError, match='회계연도'):
        filter_cash_accounts(source, target, history)
    assert target.read_bytes() == old
