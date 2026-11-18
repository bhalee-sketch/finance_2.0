import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from openpyxl import Workbook, load_workbook
from PySide6.QtTest import QTest

import qt_ui as q
from macro_reports import FOLDERS, classify
from macro_ui import open_macro


class MacroPreviewTests(TestCase):
    def test_expense_fund_rules_match_by_account(self):
        examples = {
            '지정기부금': '(지정)총학생회 기부금',
            '비등록금운영비': '(지정)Summer School 행사',
            '임의기금지급': '(임의_연구) 대학 교비',
            '대학교회한국어': '(지정)대학교회기부금',
            '연구소기부금': '(연구)연구기부금',
            '생활관입주보증금': '(일반)생활관 입주보증금',
            '제네시스랩수입': '제네시스랩(과세)',
            '기부부동산임대': '(지정) 임대료수입(현물부동산)',
            '교비일반장학금': '(지정)장학 기부금',
            'CCF후원기부금': '(지정)장학 기부금(CCF)',
            '한국어교실': '(일반)한국어교실',
        }
        accounts = [f'{name}(하나{index:05})' for index, name in enumerate(examples)]
        rows = [[account, fund.replace(' ', '\xa0')] for account, fund in zip(accounts, examples.values())]
        rows.extend([[accounts[1], '(지정)장학 기부금'], [accounts[-1], None]])
        headers = ['예적금명', '재원']
        _, exceptions, stats, _, _ = classify('expense', headers, rows, accounts=accounts)
        self.assertEqual(list(exceptions), [accounts[1], accounts[-1]])
        self.assertEqual(stats['통과'], 11)
        self.assertEqual(stats['확인 필요'], 2)
        _, full, _, _, _ = classify('expense', headers, rows, accounts=accounts, show_all=True)
        self.assertEqual(list(full), accounts)
        for account in accounts:
            self.assertIn('통과', [row[-1] for row in full[account]])

    def test_each_report_displays_data_before_excel_open(self):
        unit = '교비비등록금'
        expense_headers = ['회계단위', '재원', '차변', *[f'항목{i}' for i in range(18)], '예적금명']
        donation_headers = [f'항목{i}' for i in range(17)]
        donation_headers[15] = '잔액'
        donation = ['기부 자료', *(['']*14), 98765, '끝']
        fixtures = {
            'expense': (expense_headers,
                        [[unit, '일반재원', 32100, *(['']*18), '테스트계좌'],
                         [unit, '(연구)연구기부금', 11100, *(['']*18), '지정기부금(하나32104)']],
                        '테스트계좌', '32,100'),
            'donation': (donation_headers, [donation], '지정기부금', '98,765'),
            'fund': (['재원', '관', '목', '차변', '대변'],
                     [['임의 연구', '연구비', '재료비', 65400, 0], ['임의 연구', '연구비', '미지급금', 9000, 0]],
                     '임의_연구', '65,400'),
        }
        for kind, (headers, rows, sheet_name, expected) in fixtures.items():
            with self.subTest(kind=kind), TemporaryDirectory() as folder:
                desktop = Path(folder)
                settings = desktop/'settings'
                source = settings/FOLDERS[kind]/'원자료.xlsx'
                source.parent.mkdir(parents=True)
                self.write(source, [headers, *rows])
                self.write(settings/'accountsforfinancecode.xlsx',
                           [['회계단위', '계좌명'], [unit, '테스트계좌'], [unit, '지정기부금(하나32104)']])
                root = q.Tk()
                opener = Mock()
                try:
                    with patch('result_paths.desktop_dir', return_value=desktop), patch.object(q.messagebox, 'showerror') as error:
                        open_macro(root, lambda: desktop, lambda window, w, h: window.geometry(f'{w}x{h}'), opener, kind)
                        window = root.winfo_children()[0]
                        buttons = self.buttons(window)
                        self.assertEqual('처리계좌 선택' in buttons, kind == 'expense')
                        if kind == 'expense':
                            buttons['처리계좌 선택'].click()
                            dialog = next(child for child in window.winfo_children() if isinstance(child, q.Toplevel))
                            self.assertEqual(dialog.title(), '처리계좌 선택')
                            self.buttons(dialog)['선택 적용'].click()
                        elif kind == 'fund':
                            check = window._q.findChild(q.W.QCheckBox)
                            self.assertIn('border:2px', check.styleSheet())
                            check.click()
                        generate, excel = buttons['결과 생성'], buttons['엑셀 열기']
                        self.assertIs(generate.parentWidget(), excel.parentWidget())
                        self.assertFalse(excel.isEnabled())
                        generate.click()
                        self.wait_until(lambda: excel.isEnabled() or error.called)
                        error.assert_not_called()
                        opener.assert_not_called()
                        self.assertFalse((desktop/'검증결과').exists())
                        tabs = window._q.findChild(q.W.QTabBar)
                        self.assertEqual(tabs.tabText(tabs.currentIndex()), sheet_name)
                        model = window._q.findChild(q.W.QTableView).model()
                        self.assertIn(expected, [model.index(0, i).data() for i in range(model.columnCount())])
                        excel.click()
                        self.wait_until(lambda: opener.called or error.called, window)
                        error.assert_not_called()
                        opener.assert_called_once()
                        result = load_workbook(opener.call_args.args[0], read_only=True)
                        try:
                            self.assertIn(sheet_name, result.sheetnames)
                            if kind == 'fund':
                                self.assertEqual(result[sheet_name]['D3'].value, 65400)
                        finally:
                            result.close()
                        if kind == 'expense':
                            self.assertEqual(tabs.count(), 2)
                            options = {button.text(): button for button in window._q.findChildren(q.W.QRadioButton)}
                            options['전체보기'].click()
                            self.wait_until(lambda: excel.isEnabled() and tabs.count() == 3 or error.called, window)
                            error.assert_not_called()
                            tabs.setCurrentIndex(2)
                            self.assertIn('통과', [model.index(0, i).data() for i in range(model.columnCount())])
                            options['확인 필요만'].click()
                            self.wait_until(lambda: excel.isEnabled() and tabs.count() == 2 or error.called, window)
                            error.assert_not_called()
                finally:
                    root.destroy()

    def buttons(self, window):
        return {button.text(): button for button in window._q.findChildren(q.W.QPushButton)}

    def write(self, path, rows):
        workbook = Workbook()
        for row in rows:
            workbook.active.append(row)
        workbook.save(path)
        workbook.close()

    def wait_until(self, condition, window=None):
        for _ in range(250):
            QTest.qWait(20)
            if condition():
                return
        self.fail(window._work_status.get() if window else 'The report operation did not complete.')
