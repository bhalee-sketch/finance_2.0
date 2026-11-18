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
from loan_manager import build_uploaded_loan_report, upload_loan_sources
from scripts.build_source_release import allowed


class LoanReportTests(unittest.TestCase):
    def test_uploaded_report_is_previewed_before_excel_is_saved_and_opened(self):
        root = q.Tk()
        opener = Mock()
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        try:
            with tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source = base/'상환내역.xlsx'
                self.write_source(source, 1000)
                original = source.read_bytes()

                with patch('loan_ui.desktop_dir', return_value=base), \
                        patch('result_paths.desktop_dir', return_value=base), \
                        patch.object(q.filedialog, 'askopenfilenames', return_value=(str(source),)), \
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
                    buttons['자료 업로드'].click()
                    self.wait_until(lambda: '저장했습니다' in window._work_status.get() or show_error.called)
                    show_error.assert_not_called()
                    self.assertEqual(source.read_bytes(), original)
                    source.unlink()
                    window.destroy()
                    open_loans(root, app.center_window, opener)
                    window = root.winfo_children()[0]
                    self.assertIn('저장된 차입금 자료', window._work_status.get())
                    buttons = {button.text(): button for button in window._q.findChildren(q.W.QPushButton)}
                    generate, excel = buttons['생성'], buttons['엑셀 열기']
                    year = window._q.findChild(q.W.QSpinBox)
                    year.setValue(2025)
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
                                     ['요약', '차입금·이자 상환', '연도별현황', '분기별현황', '조회 연도 상환예정'])
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

                    results.setCurrentIndex(1)
                    detail = results.currentWidget().findChild(q.W.QTableView).model()
                    self.wait_until(lambda: detail.rowCount() == 5 or show_error.called)
                    show_error.assert_not_called()
                    self.assertEqual(detail.index(3, 1).data(), '1,000')
                    repayment_export = next(button for button in results.currentWidget().findChildren(q.W.QPushButton)
                                            if button.text() == '상환 분석 Excel 저장')
                    repayment_export.click()
                    self.wait_until(lambda: opener.call_count == 3 or show_error.called)
                    show_error.assert_not_called()
                    repayment_book = load_workbook(opener.call_args.args[0])
                    try:
                        self.assertEqual(repayment_book['분석']['B5'].value, 1000)
                    finally:
                        repayment_book.close()
                    year.setValue(2026)
                    self.assertFalse(excel.isEnabled())
                    results.setCurrentIndex(0)
                    self.assertEqual(summary.rowCount(), 0)
        finally:
            root.destroy()

    def test_latest_valid_batch_replaces_all_previous_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            storage = base/'settings'/'loan-sources.zip'
            first, second, replacement, invalid = [base/name for name in ('a.xlsx', 'b.xlsx', 'new.xlsx', 'bad.xlsx')]
            self.write_source(first, 1000)
            self.write_source(second, 500)
            self.write_source(replacement, 3000)
            self.write_source(invalid, 100, due=None)
            self.assertEqual(upload_loan_sources((first, second), storage), 2)
            previous = storage.read_bytes()
            with self.assertRaisesRegex(ValueError, '예정일'):
                upload_loan_sources((replacement, invalid), storage)
            self.assertEqual(storage.read_bytes(), previous)
            self.assertEqual(upload_loan_sources((replacement,), storage), 1)
            report = build_uploaded_loan_report(storage, 2025)
            try:
                self.assertEqual(report['2025년_분기별상환예정']['C2'].value, 3000)
                self.assertEqual(report['파일별현황'].max_row, 2)
            finally:
                report.close()

    def test_source_release_excludes_uploaded_loan_data(self):
        self.assertFalse(allowed('data/loans/originals/상환내역.xlsx'))
        self.assertFalse(allowed('settings/loan-sources.zip'))

    def write_source(self, path, amount, due=date(2025, 2, 1)):
        workbook = Workbook()
        workbook.active.append([None, due, amount, None, None, 40])
        workbook.save(path)
        workbook.close()

    def wait_until(self, condition):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            q.application().processEvents()
            if condition():
                return
            time.sleep(.01)
        self.fail('The loan report operation did not complete.')
