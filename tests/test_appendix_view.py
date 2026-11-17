import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import load_workbook
import qt_ui as q
from appendix_view import SOURCES,DATA,list_sheets,open_appendix_view
from appendix_data import load_sheet
from appendix_model import AppendixModel

class AppendixTests(unittest.TestCase):
    def test_all_record_values_match_source_data_and_top_tabs(self):
        root=q.Tk();errors=[];root.report_callback_exception=lambda *a:errors.append(str(a))
        window=open_appendix_view(root,lambda *a:None)
        tabs=window._appendix_tabs;view=window._appendix_table
        def ready(name):
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                q.application().processEvents()
                if errors:self.fail(str(errors))
                if name in window._work_status.get() and window._work_status.get().endswith('건'):return
                time.sleep(.005)
            self.fail(window._work_status.get())
        try:
            self.assertIsInstance(view.model(),AppendixModel)
            self.assertEqual(len(window._q.findChildren(q.W.QComboBox)),1)
            self.assertEqual(tabs.shape(),q.W.QTabBar.Shape.RoundedNorth)
            self.assertEqual(window._appendix_sheet_entries,[(kind,name) for kind in SOURCES for name in list_sheets(kind)])
            self.assertEqual(tabs.count(),35)
            ready(list_sheets('재무상태표')[0]);count=0
            for kind,database in SOURCES.items():
                original=next((DATA/'originals').glob(f'2025*{kind}*.xlsx'));workbook=load_workbook(original,data_only=True)
                try:
                    for sheet in workbook:
                        records=load_sheet(database,sheet.title)
                        for record in records['records']:
                            for column,value in zip(records['source_columns'],record['values']):
                                expected=sheet.cell(record['source_row'],column).value
                                if expected is not None:self.assertEqual(value,expected,(kind,sheet.title,record['source_row'],column))
                        with patch('statement_database.read_workbook',side_effect=AssertionError('Excel reconstruction')):
                            tabs.setCurrentIndex(window._appendix_sheet_entries.index((kind,sheet.title)))
                            ready(sheet.title)
                        self.assertEqual(view.model().rowCount(),len(records['records']))
                        self.assertEqual(view.model().sheet['headers'],records['headers'])
                        self.assertFalse(view.isSortingEnabled())
                        self.assertLess(tabs.mapToGlobal(q.C.QPoint()).y(),view.mapToGlobal(q.C.QPoint()).y())
                        count+=1
                finally:workbook.close()
            self.assertEqual(count,35)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
