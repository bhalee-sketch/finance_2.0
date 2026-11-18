import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import date
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from openpyxl import Workbook, load_workbook

import app
import qt_ui as q
from loan_ui import open_loans
from scripts.build_source_release import allowed


class LoanReportTests(unittest.TestCase):
    def test_bundled_report_is_previewed_before_excel_is_saved_and_opened(self):
        root = q.Tk()
        opener = Mock()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        try:
            with tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                bundled = base/'data'/'loans'/'originals'
                bundled.mkdir(parents=True)
                source = bundled/'상환내역.xlsx'
                workbook = Workbook()
                sheet = workbook.active
                sheet.append([None, date(2025, 2, 1), 1000, None, None, 40])
                workbook.save(source)
                workbook.close()
                original = source.read_bytes()

                with patch('loan_manager.BUNDLED_LOAN_DIR', bundled), \
                        patch('result_paths.desktop_dir', return_value=base), \
                        patch.object(q.messagebox, 'showerror') as show_error:
                    open_loans(root, app.center_window, opener)
                    window = root.winfo_children()[0]
                    buttons = {button.text(): button for button in window._q.findChildren(q.W.QPushButton)}
                    generate, excel = buttons['생성'], buttons['엑셀 열기']
                    self.assertNotIn('원자료 목록 새로고침', buttons)
                    self.assertNotIn('폴더 변경', buttons)
                    self.assertIs(generate.parentWidget(), excel.parentWidget())

                    year = window._q.findChild(q.W.QSpinBox)
                    year.setValue(2025)
                    self.assertFalse(excel.isEnabled())
                    generate.click()
                    self.wait_until(lambda: excel.isEnabled() or show_error.called)

                    self.assertFalse(errors)
                    show_error.assert_not_called()
                    self.assertTrue(excel.isEnabled())
                    opener.assert_not_called()
                    self.assertFalse((base/'검증결과').exists())

                    results = window._q.findChild(q.W.QTabWidget)
                    self.assertTrue(results.isVisible())
                    self.assertEqual([results.tabText(i) for i in range(results.count())],
                                     ['요약', '연도별현황', '분기별현황', '조회 연도 상환예정'])
                    summary = results.currentWidget().findChild(q.W.QTableView).model()
                    values = [summary.index(i, 0).data() for i in range(summary.rowCount())]
                    self.assertIn('총 원금', values)
                    self.assertNotIn('자료 출처', values)
                    self.assertNotIn('파일 수', values)
                    self.assertEqual(summary.index(values.index('총 원금'), 1).data(), '1,000')

                    excel.click()
                    self.wait_until(lambda: opener.called or show_error.called)
                    show_error.assert_not_called()
                    opener.assert_called_once()
                    path = opener.call_args.args[0]
                    with path.open('rb') as stream:
                        exported = load_workbook(stream, read_only=True)
                        try:
                            self.assertEqual(exported['2025년_분기별상환예정']['C2'].value, 1000)
                            self.assertEqual(exported['2025년_분기별상환예정']['C3'].value, 40)
                        finally:
                            exported.close()
                    excel.click()
                    self.assertEqual(opener.call_count, 2)
                    self.assertEqual(list(path.parent.glob('*.xlsx')), [path])
                    self.assertEqual(source.read_bytes(), original)

                    year.setValue(2026)
                    self.assertFalse(excel.isEnabled())
                    self.assertFalse(results.isVisible())
        finally:
            root.destroy()

    def test_source_release_includes_only_supported_loan_workbooks(self):
        self.assertTrue(allowed('data/loans/originals/상환내역.xlsx'))
        self.assertFalse(allowed('data/loans/originals/~$상환내역.xlsx'))
        self.assertFalse(allowed('data/loans/originals/상환내역.xlsb'))
        self.assertFalse(allowed('data/loans/private/상환내역.xlsx'))

    def wait_until(self, condition):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            q.application().processEvents()
            if condition():
                return
            time.sleep(.01)
        self.fail('The loan report operation did not complete.')
