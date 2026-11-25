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


def test_saved_statement_rolls_up_by_path_for_selected_funds(tmp_path):
    reference = history()
    other = ('다른관', EXPENSE[1], '별도행사비')
    items = reference['2025']['datasets']['전체', '합계']['items']
    items['지출', other] = {'section': '지출', 'path': other}
    source = workbook(tmp_path / '원장.xlsx', [
        (2025, *other, '사업1', '기금A', 7, 0),
        (2025, *EXPENSE, '사업1', '기금A', 10, 0),
        (2025, *ASSET, '사업2', '기금B', 20, 3),
        (2025, *EQUIPMENT, '사업2', '기금B', 5, 0),
        (2025, *EXPENSE, '사업3', '기금C', 100, 0),
    ])
    store_cashflow(tmp_path, '2025', source, reference)
    _, saved = read_cashflow(tmp_path, '2025')
    expected_expenses = {
        '관': [('관리운영비', [10, None]), ('고정자산', [None, 25]), ('다른관', [7, None])],
        '항': [('운영비 (관리운영비)', [10, None]), ('유형고정자산', [None, 25]),
              ('운영비 (다른관)', [7, None])],
        '목': [('행사비', [10, None]), ('건설중인자산', [None, 20]),
              ('기계기구매입비', [None, 5]), ('별도행사비', [7, None])],
    }
    for level, expenses in expected_expenses.items():
        funds, rows = saved.fund_statement({'기금A', '기금B'}, level)
        assert funds == ['기금A', '기금B']
        assert rows[2:] == [('자금수입총계', [0, 3]), ('[지출]', None), *expenses,
                            ('자금지출총계', [17, 25]), ('수지차액', [-17, -22])]


@pytest.mark.parametrize('stays_locked', [False, True])
def test_upload_retries_windows_lock_before_replacing_year(tmp_path, monkeypatch, stays_locked):
    from pathlib import Path
    import resource_cashflow

    folder = tmp_path / 'OneDrive' / '재원별 수지분석'
    source = sample(tmp_path / '원장.xlsx')
    reference = history()
    store_cashflow(folder, '2025', source, reference)
    target = folder / '2025.zip'
    previous = target.read_bytes()
    workbook(source, [(2025, *EXPENSE, '사업1', '', 30, 0)])
    original_replace = Path.replace
    attempts = []

    def locked_replace(archive, destination):
        assert destination == target
        assert target.read_bytes() == previous
        attempts.append(archive)
        if stays_locked or len(attempts) == 1:
            error = PermissionError('sharing violation')
            error.winerror = 32
            raise error
        return original_replace(archive, destination)

    analyze = resource_cashflow.analyze_cashflow

    def check_snapshot(snapshot, *args, **kwargs):
        assert not snapshot.is_relative_to(folder)
        assert snapshot.read_bytes() == source.read_bytes()
        return analyze(snapshot, *args, **kwargs)

    monkeypatch.setattr(resource_cashflow, 'analyze_cashflow', check_snapshot)
    monkeypatch.setattr(resource_cashflow, 'sleep', lambda delay: None)
    monkeypatch.setattr(Path, 'replace', locked_replace)
    if stays_locked:
        with pytest.raises(PermissionError, match='2025.zip 파일이 사용 중'):
            store_cashflow(folder, '2025', source, reference)
        assert target.read_bytes() == previous
    else:
        saved = store_cashflow(folder, '2025', source, reference)
        assert read_cashflow(folder, '2025') == saved
        assert saved[1].report('재원별 요약') == [('', 0, 30, -30)]
    assert len(attempts) >= 2
    assert list(folder.iterdir()) == [target]


def test_scholarship_group_reloads_and_sums_only_visible_members(tmp_path):
    from resource_cashflow import SCHOLARSHIP_GROUP, save_scholarship_funds

    source = workbook(tmp_path / '원장.xlsx', [
        (2025, *INCOME, '사업1', '재원A', 0, 100),
        (2025, *EXPENSE, '사업2', '재원B', 30, 0),
        (2025, *INCOME, '사업2', SCHOLARSHIP_GROUP, 0, -5),
        (2025, *INCOME, '사업2', '(일반)기타자금', 0, 70),
    ])
    _, original = store_cashflow(tmp_path, '2025', source, history())
    save_scholarship_funds(tmp_path, '2025', {'재원A', '재원B'})
    _, grouped = read_cashflow(tmp_path, '2025')
    assert grouped.report('재원별 요약') == [(SCHOLARSHIP_GROUP, 95, 30, 65), ('(일반)기타자금', 70, 0, 70)]
    assert grouped.report('대사업별 요약') == original.report('대사업별 요약')
    for level in ('관', '항', '목'):
        funds, rows = grouped.fund_statement(level=level)
        assert funds == [SCHOLARSHIP_GROUP, '(일반)기타자금']
        assert dict(rows)['자금수입총계'] == [95, 70]
        assert dict(rows)['자금지출총계'] == [30, 0]
        assert dict(rows)['수지차액'] == [65, 70]
        funds, rows = grouped.fund_statement({'재원B'}, level)
        assert funds == [SCHOLARSHIP_GROUP] and rows[-1] == ('수지차액', [-30])
    _, replaced = store_cashflow(tmp_path, '2025', source, history())
    assert replaced == grouped
    assert store_cashflow(tmp_path, '2026', source, history())[1] == original
    save_scholarship_funds(tmp_path, '2025', set())
    assert read_cashflow(tmp_path, '2025')[1] == original


def test_statement_hides_only_funds_with_no_nonzero_account_at_displayed_level(tmp_path):
    from resource_cashflow import SCHOLARSHIP_GROUP

    report = analyze_cashflow(workbook(tmp_path / '원장.xlsx', [
        (2025, *EXPENSE, '사업1', '거래없음', 0, 0),
        (2025, *INCOME, '사업1', '장학A', 0, 90),
        (2025, *INCOME, '사업2', '장학B', 90, 0),
        (2025, *INCOME, '사업1', '수지균형', 0, 50),
        (2025, *EXPENSE, '사업1', '수지균형', 50, 0),
        (2025, *ASSET, '사업1', '지출상계', 20, 0),
        (2025, *EQUIPMENT, '사업1', '지출상계', 0, 20),
    ]), history())
    report.scholarship_funds = frozenset({'장학A', '장학B'})
    for level in ('관', '항', '목'):
        funds, rows = report.fund_statement(level=level)
        assert funds == (['수지균형', '지출상계'] if level == '목' else ['수지균형'])
        assert sum(dict(rows)['자금수입총계']) == sum(dict(rows)['자금지출총계']) == 50
        assert report.fund_statement('거래없음', level)[0] == []
        assert report.fund_statement('장학B', level)[0] == [SCHOLARSHIP_GROUP]


def test_zero_balance_filter_applies_after_grouping_and_fund_selection(tmp_path):
    from resource_cashflow import SCHOLARSHIP_GROUP

    report = analyze_cashflow(workbook(tmp_path / '원장.xlsx', [
        (2025, *INCOME, '사업1', '장학A', 0, 30),
        (2025, *EXPENSE, '사업1', '장학B', 30, 0),
        (2025, *INCOME, '사업2', '일반', 0, 50),
        (2025, *EXPENSE, '사업3', '기타', 20, 0),
    ]), history())
    report.scholarship_funds = frozenset({'장학A', '장학B'})
    for level in ('관', '항', '목'):
        funds, rows = report.fund_statement(level=level, exclude_zero_balance=True)
        assert funds == ['기타', '일반']
        assert dict(rows)['수지차액'] == [-20, 50]
        assert dict(rows)['자금수입총계'] == [0, 50]
        assert dict(rows)['자금지출총계'] == [20, 0]
        assert report.fund_statement('장학B', level, exclude_zero_balance=True)[0] == [SCHOLARSHIP_GROUP]
        assert report.fund_statement(level=level)[0][0] == SCHOLARSHIP_GROUP
    assert report.report('재원별 요약', exclude_zero_balance=True) == [('기타', 0, 20, -20), ('일반', 50, 0, 50)]
    assert report.report('대사업별 요약', exclude_zero_balance=True) == [('사업2', 50, 0, 50), ('사업3', 0, 20, -20)]
