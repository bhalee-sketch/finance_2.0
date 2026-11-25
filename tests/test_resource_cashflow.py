from openpyxl import Workbook
import pytest

from resource_cashflow import REQUIRED, analyze_cashflow, read_cashflow, saved_cashflow_years, store_cashflow


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
    for view in ('재원별 요약', '대사업별 요약'):
        assert [sum(row[i] for row in report.report(view)) for i in (-3, -2, -1)] == [961, 295, 666]


def test_cashflow_rejects_unusable_uploads(tmp_path):
    path = tmp_path / '원장.xlsx'
    with pytest.raises(ValueError, match='차변'):
        analyze_cashflow(workbook(path, [], REQUIRED[:-2]), history())
    with pytest.raises(ValueError, match='3행'):
        analyze_cashflow(workbook(path, [(2025, *INCOME, '', '', 0, 1), (2026, *INCOME, '', '', 0, 1)]), history())
    with pytest.raises(ValueError, match='차변·대변'):
        analyze_cashflow(workbook(path, [(2025, *EXPENSE, '', '', '오류', 0)]), history())


def test_saved_fiscal_years_are_independent_and_invalid_replacement_is_atomic(tmp_path):
    from zipfile import ZipFile

    folder = tmp_path / 'settings' / '재원별 수지분석'
    source = sample(tmp_path / '교비.xlsx')
    reference = history()
    reference['2026'] = reference['2025']
    first = store_cashflow(folder, '2025', source, reference)
    assert first[1].year == '2026' and first[1].basis == '2025'
    with ZipFile(folder / '2025.zip') as archive:
        assert archive.read('workbook.xlsx') == source.read_bytes()
    second = store_cashflow(folder, '2026', source, reference)
    assert saved_cashflow_years(folder) == ['2026', '2025']
    source.unlink()
    assert read_cashflow(folder, '2025') == first
    invalid = workbook(source, [(2025, *EXPENSE, '', '', '오류', 0)])
    with pytest.raises(ValueError):
        store_cashflow(folder, '2025', invalid, reference)
    assert read_cashflow(folder, '2025') == first
    replacement = workbook(source, [(2025, *EXPENSE, '사업1', '', 30, 0)])
    store_cashflow(folder, '2025', replacement, reference)
    assert read_cashflow(folder, '2025')[1].report('대사업별 요약') == [('사업1', 0, 30, -30)]
    assert read_cashflow(folder, '2026') == second


def test_multiple_funds_share_projects_and_include_unassigned(tmp_path):
    report = analyze_cashflow(workbook(tmp_path / '원장.xlsx', [
        (2026, *INCOME, '사업1', '기금A', 0, 100),
        (2026, *INCOME, '사업1', '', 0, 50),
        (2026, *INCOME, '사업2', '기금A', 0, 30),
        (2026, *EXPENSE, '사업1', '', 20, 0),
        (2026, *EXPENSE, '사업2', '기금B', 40, 0),
    ]), history())
    funds = {'기금A', ''}
    columns, rows = report.fund_statement(funds)
    assert columns == ['기금A', '']
    assert rows[-1] == ('수지차액', [130, 30])
    assert report.report('대사업별 요약', funds) == [('사업1', 150, 20, 130), ('사업2', 30, 0, 30)]
    assert report.report('재원별 요약', funds) == [('', 50, 20, 30), ('기금A', 130, 0, 130)]


def test_statement_summary_separates_sides_and_reconciles_every_fund(tmp_path):
    report = analyze_cashflow(sample(tmp_path / '원장.xlsx'), history())
    columns, rows = report.fund_statement()
    assert columns == ['기금A', '기금B', '']
    assert rows == [
        ('[수입]', None), ('교육부', [950, None, None]),
        ('건설중인자산', [None, None, 11]),
        ('자금수입총계', [950, 0, 11]), ('[지출]', None),
        ('행사비', [180, 40, None]), ('건설중인자산', [None, None, 50]),
        ('기계기구매입비', [25, None, None]),
        ('자금지출총계', [205, 40, 50]), ('수지차액', [745, -40, -39]),
    ]
    columns, rows = report.fund_statement('기금A')
    assert columns == ['기금A'] and rows[-1] == ('수지차액', [745])


def test_saved_statement_distinguishes_same_mok_in_different_paths(tmp_path):
    reference = history()
    other = (EXPENSE[0], '별도운영비', EXPENSE[2])
    items = reference['2025']['datasets']['전체', '합계']['items']
    items['지출', other] = {'section': '지출', 'path': other}
    source = workbook(tmp_path / '원장.xlsx', [
        (2025, *other, '사업1', '기금B', 20, 0),
        (2025, *EXPENSE, '사업1', '기금A', 10, 0),
    ])
    store_cashflow(tmp_path, '2025', source, reference)
    _, saved = read_cashflow(tmp_path, '2025')
    _, rows = saved.fund_statement({'기금A', '기금B'})
    assert rows[-4:] == [('행사비 (관리운영비 / 운영비)', [10, None]),
                         ('행사비 (관리운영비 / 별도운영비)', [None, 20]),
                         ('자금지출총계', [10, 20]), ('수지차액', [-10, -20])]
