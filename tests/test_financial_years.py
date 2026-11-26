import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,unittest,sqlite3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from statement_database import discover_statements,load_record
from appendix_view import SOURCES,available_years,list_sheets,open_appendix_view
from appendix_data import load_sheet

class FinancialYearTests(unittest.TestCase):
    def test_all_years_and_appendix_data_load(self):
        self.assertEqual(available_years(),['2025','2024','2023','2022','2021'])
        self.assertEqual(list(discover_statements()),['2025','2024','2023','2022','2021','2020','2019','2018'])
        from statement_loader import load_statement_record_from_path
        for year in ['2018','2019','2020']:
            source=discover_statements()[year]
            self.assertEqual(load_record(source),load_statement_record_from_path(source.parent/'originals'/f'{year}회계연도.xlsx'))
            self.assertEqual(len(load_record(source)['sheets']),12)
        for year in ['2021','2022','2023','2024','2025']:
            self.assertEqual(len(load_record(discover_statements()[year])['sheets']),12)
            for category,database in SOURCES.items():
                sheets=list_sheets(category,year)
                self.assertEqual(len(sheets),29 if category=='재무상태표' else 6)
                for name in sheets:
                    data=load_sheet(database,name,year)
                    self.assertTrue(data['headers'],(year,name))
                    self.assertTrue(data['records'],(year,name))

    def test_appendix_year_switch_replaces_sheet_records(self):
        root=q.Tk();errors=[];root.report_callback_exception=lambda *a:errors.append(str(a))
        window=open_appendix_view(root,lambda *a:None)
        def wait(year):
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                q.application().processEvents()
                if errors:self.fail(str(errors))
                if window._work_status.get().startswith(year+'년') and window._work_status.get().endswith('건'):return
                time.sleep(.005)
            self.fail(window._work_status.get())
        try:
            wait('2025')
            for year in ['2024','2023','2022','2021','2025']:
                window._appendix_year.set(year);window._appendix_year.event_generate('<<ComboboxSelected>>');wait(year)
                self.assertEqual(window._appendix_tabs.count(),35)
                category,name=window._appendix_sheet_entries[0]
                self.assertEqual(window._appendix_model.sheet,load_sheet(SOURCES[category],name,year))
        finally:root.destroy()

if __name__=='__main__':unittest.main()
