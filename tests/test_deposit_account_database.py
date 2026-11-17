import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,time,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from deposit_accounts import load_accounts,DATABASE,import_accounts
from deposit_plan import read_catalog
from deposit_ui import open_deposit

class DepositDatabaseTests(unittest.TestCase):
    def test_original_accounts_match_database(self):
        source=DATABASE.parent/'originals'/'regular account.xls'
        self.assertEqual(load_accounts(),read_catalog(source,False))
        self.assertEqual(len(load_accounts()),42)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'accounts.sqlite3'
            first=import_accounts(source,target)
            self.assertEqual(first,import_accounts(source,target))
            self.assertEqual(load_accounts(target),load_accounts())

    def test_ui_reads_db_without_pc_account_file(self):
        root=q.Tk();errors=[];root.report_callback_exception=lambda *a:errors.append(str(a))
        try:
            with tempfile.TemporaryDirectory() as folder:
                open_deposit(root,lambda:Path(folder),lambda w,x,y:w.geometry(f'{x}x{y}'),lambda *a:None)
                window=next(w for w in root.children.values() if isinstance(w,q.Toplevel))
                end=time.monotonic()+5
                while time.monotonic()<end:
                    q.application().processEvents()
                    if errors:self.fail(str(errors))
                    labels=[w.text() for w in window._q.findChildren(q.W.QLabel)]
                    if any('원금 이체계좌 42개' in text for text in labels):break
                    time.sleep(.01)
                else:self.fail('Database accounts were not loaded')
                self.assertTrue(any('정기 75개' in text for text in labels))
        finally:root.destroy()

if __name__=='__main__':unittest.main()
