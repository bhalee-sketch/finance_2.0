import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
import unittest
from unittest.mock import patch

from openpyxl import load_workbook
from statement_database import discover_statements, load_record, export_source
from statement_loader import load_statement_record_from_path
from statement_exporter import TYPE_LABEL, SCOPE_SUFFIX, _build_filtered_sheets, export_statement_excel

ROOT = Path(__file__).resolve().parents[1]


class DatabaseTests(unittest.TestCase):
    def test_original_parity_and_exports(self):
        source = discover_statements()['2025']
        record = load_record(source)
        self.assertEqual(record, load_statement_record_from_path(
            ROOT / 'data/statements/originals/2025회계연도.xlsx'))
        bundle = {'by_year': {'2025': record}}
        with tempfile.TemporaryDirectory() as folder:
            for kind in TYPE_LABEL:
                for scope in SCOPE_SUFFIX:
                    parts = ['all'] if kind == 'trial' else ['all', 'upper', 'lower']
                    for part in parts:
                        self.assertTrue(_build_filtered_sheets(bundle, '2025', kind, scope, part))
                    target = Path(folder) / f'{kind}-{scope}.xlsx'
                    export_statement_excel(bundle, source.parent, '2025', kind, scope, 'all', output_path=target)
                    book = load_workbook(target)
                    self.assertTrue(book.active.max_row > 1)
                    book.close()

    def test_full_export_without_original(self):
        from statement_print_export import ExcelExportWorker
        with tempfile.TemporaryDirectory() as folder, patch('statement_loader.load_workbook', side_effect=AssertionError('Original Excel accessed')):
            source = discover_statements()['2025']
            self.assertEqual(len(load_record(source)['sheets']), 12)
            with export_source(source) as snapshot:
                self.assertTrue(snapshot.exists())
                target = Path(folder) / 'full.xlsx'
                worker = ExcelExportWorker(snapshot, str(target))
                results = []
                worker.finished.connect(lambda ok, message: results.append((ok, message)))
                worker.run()
                self.assertTrue(results[-1][0], results)
                book = load_workbook(target)
                self.assertEqual(len(book.sheetnames), 12)
                book.close()
            self.assertFalse(snapshot.exists())

    def test_ui_uses_database(self):
        import qt_ui as q
        from statement_ui import open_statement_view
        errors = []
        root = q.Tk()
        root.report_callback_exception = lambda *args: errors.append(str(args))
        def pump_ready(window):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                q.application().processEvents()
                text = window._work_status.get()
                if '행' in text and '중' not in text:
                    return text
                if errors:
                    self.fail(str(errors))
                time.sleep(.01)
            self.fail(window._work_status.get())
        try:
            with patch.object(q.messagebox, 'showerror', side_effect=lambda *a, **k: errors.append(str(a))), patch(
                    'statement_loader.load_workbook', side_effect=AssertionError('Original Excel accessed')):
                open_statement_view(root, lambda: (_ for _ in ()).throw(AssertionError('PC desktop accessed')),
                                    lambda *a: None, lambda *a: None)
                window = next(w for w in root.children.values() if isinstance(w, q.Toplevel))
                self.assertIn('2025', pump_ready(window))
                selectors = {w.accessibleName(): w for w in q.application().allWidgets()
                             if isinstance(w, q.W.QComboBox) and w.accessibleName()}
                self.assertEqual(selectors['회계연도'].currentText(), '2025')
                for kind in TYPE_LABEL.values():
                    for scope in SCOPE_SUFFIX.values():
                        for name, value in [('구분', kind), ('단위', scope)]:
                            widget = selectors[name]
                            widget.setCurrentText(value)
                            widget.activated.emit(widget.currentIndex())
                            pump_ready(window)
                        self.assertIn('2025', window._work_status.get())
                self.assertFalse(errors)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
