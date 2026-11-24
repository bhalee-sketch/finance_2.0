from openpyxl import Workbook
import pytest

from resource_cashflow import REQUIRED, analyze_cashflow


INCOME = ('전입및기부수입', '국고보조금', '교육부')
EXPENSE = ('관리운영비', '운영비', '행사비')
ASSET = ('고정자산', '유형고정자산', '건설중인자산')
INTEREST = ('교육외수입', '예금이자수입', '예금이자 수입')
EQUIPMENT = ('고정자산', '유형고정자산', '기계기구매입비')


def history():
    accounts = [('수입', INCOME), ('수입', INTEREST), ('지출', EXPENSE),
                ('수입', ASSET), ('지출', ASSET), ('지출', EQUIPMENT)]
    items = {(side, path): {'section': side, 'path': path} for side, path in accounts}
    return {'2025': {'datasets': {('전체', '합계'): {'items': items}}}}


def workbook(path, records, headers=REQUIRED):
    book = Workbook()
    sheet = book.active
    sheet.append(headers)
    for record in records:
        sheet.append(record)
    book.save(path)
    return path


def sample(path):
    return workbook(path, [
        (2026, *INCOME, '사업1', '기금A', 0, '1,000'),
        (2026, *INCOME, '사업1', '기금A', 0, -50),
        (2026, *EXPENSE, '사업1', '기금A', 200, 20),
        (2026, *EXPENSE, '사업2', '기금B', 40, 0),
        (2026, *ASSET, '', '', 50, 11),
        (2026, *INTEREST[:2], '예금이자', '', '', 0, 9),
        (2026, '교육외 수입', *INTEREST[1:], '사업1', '기금A', 0, 21),
        (2026, *EQUIPMENT[:2], '기계기구', '사업1', '기금A', 25, 0),
        (2026, '유동자산', '유동자금', '예금', '사업1', '기금A', 1000, 0),
        (2026, '다른관', '국고보조금', '교육부', '', '', 0, 1000),
    ])


def test_cashflow_reconciles_across_views(tmp_path):
    report = analyze_cashflow(sample(tmp_path / '원장.xlsx'), history())
    assert (report.year, report.basis, report.included, report.excluded) == ('2026', '2025', 6, 4)
    assert report.report('재원별 요약', '') == [('', 11, 50, -39)]
    assert report.report('대사업별 요약', '기금A') == [('사업1', 950, 205, 745)]
    details = report.report('계정·대사업별 상세')
    assert ('지출', *EQUIPMENT, '사업1', 0, 25, -25) in details
    assert ('수입', *ASSET, '', 11, 0, 11) in details
    assert ('지출', *ASSET, '', 0, 50, -50) in details
    for view in ('재원별 요약', '대사업별 요약', '계정·대사업별 상세'):
        assert [sum(row[i] for row in report.report(view)) for i in (-3, -2, -1)] == [961, 295, 666]


def test_cashflow_rejects_unusable_uploads(tmp_path):
    path = tmp_path / '원장.xlsx'
    with pytest.raises(ValueError, match='차변'):
        analyze_cashflow(workbook(path, [], REQUIRED[:-2]), history())
    with pytest.raises(ValueError, match='3행'):
        analyze_cashflow(workbook(path, [(2025, *INCOME, '', '', 0, 1), (2026, *INCOME, '', '', 0, 1)]), history())
    with pytest.raises(ValueError, match='차변·대변'):
        analyze_cashflow(workbook(path, [(2025, *EXPENSE, '', '', '오류', 0)]), history())


def test_statement_summary_separates_sides_and_reconciles_every_project(tmp_path):
    report = analyze_cashflow(sample(tmp_path / '원장.xlsx'), history())
    projects, rows = report.project_statement()
    assert projects == ['사업1', '사업2', '']
    assert rows == [
        ('[수입]', None), ('전입및기부수입', [950, None, None]),
        ('고정자산', [None, None, 11]),
        ('자금수입총계', [950, 0, 11]), ('[지출]', None),
        ('관리운영비', [180, 40, None]), ('고정자산', [25, None, 50]),
        ('자금지출총계', [205, 40, 50]), ('수지차액', [745, -40, -39]),
    ]
    projects, rows = report.project_statement('기금A')
    assert projects == ['사업1'] and rows[-1] == ('수지차액', [745])
