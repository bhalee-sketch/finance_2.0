from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dashboard_calendar import CHECK, HEADERS, PlannerStore
from dashboard_finance import SCOPES, _load, complete_sum, difference, load_dashboard, millions, won, year_end
from dashboard_loans import detail_for
from work_records import RecordBook


class DashboardTests(TestCase):
    def test_verified_closing_and_account_scopes(self):
        data = load_dashboard()
        self.assertEqual(data.years, tuple(range(2021, 2026)))
        expected = {
            '전체': (115058691265, 148323276214, (96832342401, 83786206250), 25010878121, 7225009890),
            '등록금': (32480989816, 82326229945, (32278896840, 38334146639), 0, 0),
            '비등록금': (83077701449, 119614954592, (65053445561, 45952059611), 25010878121, 7225009890),
        }
        for scope in SCOPES:
            for year in data.years:
                period = data.periods[year, scope]
                self.assertEqual(difference(*period.cash), 0)
                self.assertFalse(period.errors)
            year, balance = data.latest_balance(scope)
            self.assertEqual(year_end(year), date(2026, 2, 28))
            self.assertTrue(all(v == 0 for v in balance.checks.values()))
            self.assertEqual((period.cash[0], balance.left_total, period.operation, balance.fund,
                              complete_sum(balance.loan_parts)), expected[scope])
        self.assertTrue(data.latest_balance('등록금')[1].rounding_note)
        self.assertEqual(millions(Decimal('1500000')), 2)
        self.assertEqual(millions(Decimal('-500000')), -1)

    def test_missing_years_unmatched_totals_and_explicit_zero(self):
        files = {'2025':'new', '2023':'older'}
        def sheets(source, predicate):
            return [('자금계산서(전체)', [['계정','결산'],['하위계정',400],['자금수입총계',10],
                                          ['자금지출총계',9 if source=='new' else 10]], {})]
        with patch('dashboard_finance.discover_statements', return_value=files), \
                patch('dashboard_finance.iter_analysis_sheets', side_effect=sheets):
            data = _load('only-for-missing-year-test', 1, date(2026,11,27))
            interim = _load('only-for-interim-year-test', 1, date(2025,6,30))
        self.assertEqual(data.years, tuple(range(2021,2026)))
        self.assertNotIn((2024,'전체'), data.periods)
        self.assertEqual(interim.periods[2025,'전체'].cash, (None,None))
        self.assertIn('미확정', interim.periods[2025,'전체'].errors['자금계산서'])
        self.assertEqual(data.periods[2025,'전체'].cash, (10,9))
        self.assertEqual(data.latest_balance('전체'), (None,None))
        self.assertEqual(won(None), '자료 없음')
        self.assertEqual(won(Decimal(0)), '0원')
        self.assertIsNone(complete_sum((1,None)))
        self.assertIsNone(complete_sum([]))

    def test_lender_reconciliation_and_registered_installments(self):
        data = load_dashboard()
        with TemporaryDirectory() as folder:
            storage = Path(folder)/'loan-sources.zip'
            for scope in SCOPES:
                contracts, rows, lenders, total, alerts = detail_for(data,2025,scope,storage)
                self.assertEqual(total, complete_sum(data.periods[2025,scope].balance.loan_parts))
                if scope=='등록금':
                    self.assertEqual((contracts,rows,lenders,total), ([],[],{},0))
                    continue
                self.assertEqual(lenders, {'한국사학진흥재단':7225009890})
                self.assertEqual(len({c['name'] for c in contracts}), 7)
                self.assertEqual(sum(c['balance'] for c in contracts), total)
                self.assertEqual(len(rows),47)
                dates = [r[0] for r in rows]
                self.assertEqual(dates, sorted(dates))
                self.assertGreater(min(dates), year_end(2025))
                for _,_,_,principal,interest,installment in rows:
                    self.assertEqual(complete_sum((principal,interest)), installment)

    def test_shared_calendar_and_checklist_survive_reopen(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)/'업무 기록.sqlite3'
            store = PlannerStore(path)
            day = date(2026,11,27)
            book = RecordBook(path)
            with book.transaction() as db:
                key = db.execute("INSERT INTO tasks(name) VALUES('기존 업무')").lastrowid
                db.executemany('INSERT INTO grid_cells VALUES(?,0,?,?)',
                               ((key,i,v) for i,v in enumerate(HEADERS[:4])))
                db.executemany('INSERT INTO grid_cells VALUES(?,1,?,?)',
                               ((key,0,day.isoformat()),(key,1,'기존 일정')))
            store.save(None, {0:day.isoformat(),1:'새 일정',4:'09:00',5:'10:00',6:'일정'})
            store.save(None, {0:day.isoformat(),1:'확인 업무',6:CHECK})
            rows = dict((values[1],key) for key,values in store.month(day))
            self.assertEqual(set(rows), {'기존 일정','새 일정','확인 업무'})
            store.save(rows['확인 업무'], {3:'완료'})
            next_month = date(2026,12,1)
            store.save(rows['기존 일정'], {0:next_month.isoformat()})
            reopened = PlannerStore(path)
            self.assertEqual(reopened.month(next_month)[0][0], (key,1))
            self.assertEqual(dict(reopened.month(day))[rows['확인 업무']][3],'완료')

    def test_filter_at_load_time_and_mismatch_rendering(self):
        import qt_ui as qt
        from dashboard_finance import DashboardData, Period
        from home_dashboard import Dashboard

        qt.application()
        with TemporaryDirectory() as folder, patch('home_dashboard.background') as worker:
            home = Dashboard(Path(folder), lambda *args: None)
            try:
                home.planner.select(date(2024,2,29))
                home.selector.setCurrentIndex(2)
                snapshot = DashboardData(tuple(range(2021,2026)), {
                    (2025,'비등록금'): Period(cash=(120,110)), (2025,'전체'): Period(cash=(0,0))})
                worker.call_args.args[2](snapshot)
                self.assertIn('차이 10원', home.cash.note.text())
                self.assertEqual(home.trends['cash'].rows[-1], (2025,(None,)))
                home.selector.setCurrentIndex(0)
                self.assertEqual(home.trends['cash'].rows[-1], (2025,(0,)))
                self.assertIn('2024 자료 없음', home.cash.note.text())
                self.assertEqual(home.loan_amount.text(), '자료 없음')
                self.assertEqual(home.planner.day, date(2024,2,29))
            finally:
                home.close()

    def test_open_loan_view_ignores_superseded_scope(self):
        import qt_ui as qt
        from dashboard_loan_view import ClosingLoanView

        qt.application()
        data = load_dashboard()
        with TemporaryDirectory() as folder, patch('dashboard_loan_view.background') as worker:
            view = ClosingLoanView(Path(folder)/'loan-sources.zip')
            try:
                view.display(data,2025,'전체')
                old = worker.call_args.args[2]
                view.display(data,2025,'등록금')
                worker.call_args.args[2](([], [], {}, Decimal(0), []))
                old(([], [], {'다른 차입처': Decimal(40)}, Decimal(40), []))
                self.assertIn('등록금회계', view.caption.text())
                self.assertEqual(view.groups.item(0,1).text(), '0원')
                self.assertEqual(view.lenders.count(), 1)
            finally:
                view.close()
