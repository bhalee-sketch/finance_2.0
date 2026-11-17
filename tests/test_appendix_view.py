import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openpyxl import load_workbook
import qt_ui as q
from appendix_view import SOURCES, DATA, list_sheets, open_appendix_view
from statement_loader import _cell_display_text


class AppendixTests(unittest.TestCase):
    def test_all_sheets_match_original_in_view(self):
        root = q.Tk()
        errors = []
        root.report_callback_exception = lambda *a: errors.append(str(a))
        window = open_appendix_view(root, lambda *a: None)
        kind_box, sheet_box = window._appendix_selectors
        table = window._appendix_table
        def ready(name):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                q.application().processEvents()
                if errors:self.fail(str(errors))
                if name in window._work_status.get() and window._work_status.get().endswith('행'):
                    return
                time.sleep(.005)
            self.fail(window._work_status.get())
        try:
            self.assertEqual([kind_box._q.itemText(i) for i in range(2)], ['재무상태표', '운영계산서'])
            ready(list_sheets('재무상태표')[0])
            count = 0
            for kind in SOURCES:
                kind_box.set(kind)
                kind_box.event_generate('<<ComboboxSelected>>')
                ready(list_sheets(kind)[0])
                original = next((DATA / 'originals').glob(f'*{kind}*.xlsx'))
                workbook = load_workbook(original, data_only=True)
                try:
                    self.assertEqual(list_sheets(kind), workbook.sheetnames)
                    for sheet in workbook:
                        sheet_box.set(sheet.title)
                        sheet_box.event_generate('<<ComboboxSelected>>')
                        # The same sheet can have the same title in a later workbook.
                        ready(sheet.title)
                        self.assertEqual(table.rowCount(), sheet.max_row)
                        self.assertEqual(table.columnCount(), sheet.max_column)
                        self.assertFalse(table.isSortingEnabled())
                        for row in sheet:
                            for cell in row:
                                item = table.item(cell.row-1, cell.column-1)
                                self.assertEqual(item.text() if item else '', _cell_display_text(cell),
                                                 (kind, sheet.title, cell.coordinate))
                        for merged in sheet.merged_cells.ranges:
                            self.assertEqual(table.rowSpan(merged.min_row-1, merged.min_col-1), merged.max_row-merged.min_row+1)
                            self.assertEqual(table.columnSpan(merged.min_row-1, merged.min_col-1), merged.max_col-merged.min_col+1)
                        count += 1
                finally:
                    workbook.close()
            self.assertEqual(count, 36)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
