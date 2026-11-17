import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,sqlite3,tempfile,time,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
import qt_ui as q
from fixed_deposit_database import normalize_source,import_fixed_accounts,load_fixed_accounts,DATABASE
from deposit_plan import read_catalog
from deposit_ui import open_deposit

class FixedUpdateTests(unittest.TestCase):
    def test_supplied_reference_parity(self):
        accounts,excluded=normalize_source(DATABASE.parent/'originals'/'원본 FIXED.xls')
        reference=read_catalog(DATABASE.parent/'originals'/'fixed-reference.xls',True)
        self.assertEqual(set(accounts),set(reference));self.assertEqual(len(accounts),75)
        for key,item in reference.items():
            for field,value in item.items():self.assertEqual(accounts[key][field],value)
        self.assertEqual(load_fixed_accounts(),accounts)
        self.assertEqual(sum(excluded.values())+len(accounts),272)

    def test_monthly_history_and_failed_update_preserves_previous(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);database=folder/'catalog.sqlite3'
            def write(value):
                file=folder/'monthly.xlsx';book=Workbook();sheet=book.active
                sheet.append(['예금종류','사용여부','계약금액','계좌번호','회계단위','예치기관','예적금명','해약일','만기일'])
                sheet.append(['정기예금','사용',value,'001-01','2112 교비비등록금','KEB하나은행','정기예금',' . . ','2027.01.01'])
                sheet.append(['보통예금','사용',100,'002','2112 교비비등록금','KEB하나은행','보통예금','',''])
                book.save(file);book.close();return file
            import_fixed_accounts(write(100),database)
            import_fixed_accounts(write(200),database)
            self.assertEqual(load_fixed_accounts(database)['00101']['principal'],200)
            self.assertEqual(load_fixed_accounts(database)['00101']['unit'],'교비비')
            with sqlite3.connect(database) as c:self.assertEqual(c.execute('select count(*) from imports').fetchone()[0],2)
            with self.assertRaises(ValueError):import_fixed_accounts(write(-1),database)
            self.assertEqual(load_fixed_accounts(database)['00101']['principal'],200)

    def test_settings_upload_and_plan_button_location(self):
        root=q.Tk();errors=[];root.report_callback_exception=lambda *a:errors.append(str(a))
        try:
            with tempfile.TemporaryDirectory() as folder:
                folder=Path(folder)
                open_deposit(root,lambda:folder,lambda w,x,y:w.geometry(f'{x}x{y}'),lambda *a:None)
                window=next(w for w in root.children.values() if isinstance(w,q.Toplevel))
                def wait(predicate):
                    end=time.monotonic()+5
                    while time.monotonic()<end:
                        q.application().processEvents()
                        if errors:self.fail(str(errors))
                        if predicate():return
                        time.sleep(.01)
                    self.fail('Timed out')
                wait(lambda:not window._read_task.busy)
                # Initial delayed catalog load must also finish before uploading.
                wait(lambda:any('정기 75개' in w.text() for w in window._q.findChildren(q.W.QLabel)))
                buttons={w.text():w for w in window._q.findChildren(q.W.QPushButton)}
                self.assertNotIn('계좌 새로고침',buttons)
                self.assertEqual(sum('계획표 생성' in name for name in buttons),1)
                with patch.object(q.filedialog,'askopenfilename',return_value=str(DATABASE.parent/'originals'/'원본 FIXED.xls')):
                    buttons['자료 설정'].click()
                wait(lambda:hasattr(window,'_latest_fixed_import') and not window._read_task.busy)
                self.assertEqual(window._latest_fixed_import['accounts'],75)
                local=folder/'settings'/'deposit plan'/'fixed_accounts.sqlite3'
                self.assertTrue(local.is_file());self.assertEqual(len(load_fixed_accounts(local)),75)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
