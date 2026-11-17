import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,time,unittest,sqlite3
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
import qt_ui as q
from transfer_accounts import DATABASE,normalize_source,read_accounts,import_accounts
from transfer_text import load_accounts
from transfer_ui import open_transfer

class TransferUpdateTests(unittest.TestCase):
    def test_supplied_reference_parity(self):
        actual,excluded=normalize_source(DATABASE.parent/'originals'/'원본.xls')
        expected=load_accounts(DATABASE.parent/'originals'/'원본수정.xls')
        self.assertEqual([(a['name'],a['number']) for a in actual],[(a['name'],a['number']) for a in expected])
        self.assertEqual(len(actual),221);self.assertEqual(excluded,{'법인팀':42,'복지회':9})
        self.assertEqual(read_accounts(),actual)

    def test_monthly_snapshots_and_invalid_file(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);database=folder/'accounts.sqlite3'
            def write(name):
                source=folder/'monthly.xlsx';book=Workbook();sheet=book.active
                sheet.append(['관리부서','예적금명','계좌번호'])
                sheet.append(['재무회계팀',name,'001-00123'])
                sheet.append(['법인팀','제외계좌','002'])
                book.save(source);book.close();return source
            import_accounts(write('첫 계좌'),database)
            import_accounts(write('갱신 계좌'),database)
            self.assertEqual(read_accounts(database)[0]['name'],'갱신 계좌')
            self.assertEqual(read_accounts(database)[0]['number'],'001-00123')
            with sqlite3.connect(database) as c:self.assertEqual(c.execute('select count(*) from imports').fetchone()[0],2)
            invalid=folder/'bad.xlsx';book=Workbook();book.active.append(['알수없는열']);book.save(invalid);book.close()
            with self.assertRaises(ValueError):import_accounts(invalid,database)
            self.assertEqual(read_accounts(database)[0]['name'],'갱신 계좌')

    def test_upload_compact_inputs_and_reset(self):
        root=q.Tk();errors=[];root.report_callback_exception=lambda *a:errors.append(str(a))
        try:
            with tempfile.TemporaryDirectory() as folder:
                folder=Path(folder)
                open_transfer(root,lambda:folder,lambda w,x,y:w.geometry(f'1600x{y}'),lambda *a:None)
                window=next(w for w in root.children.values() if isinstance(w,q.Toplevel))
                def wait(predicate):
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        q.application().processEvents()
                        if errors:self.fail(str(errors))
                        if predicate():return
                        time.sleep(.01)
                    self.fail(window._work_status.get())
                wait(lambda:window._work_status.get().startswith('계좌 221개'))
                buttons={w.text():w for w in window._q.findChildren(q.W.QPushButton)}
                self.assertNotIn('새로고침',buttons);self.assertNotIn('입력 비우기',buttons)
                fields={w.accessibleName():w for w in window._q.findChildren(q.W.QLineEdit) if w.accessibleName()}
                for field in fields.values():self.assertLessEqual(field.width(),440)
                accounts=read_accounts()
                fields['출금계좌'].setText(accounts[0]['name']);fields['입금계좌'].setText(accounts[1]['name'])
                buttons['문구 생성'].click()
                self.assertTrue(window._work_status.get().startswith('문구 1개'))
                buttons['초기화'].click()
                self.assertEqual(fields['출금계좌'].text(),'');self.assertEqual(fields['입금계좌'].text(),'')
                self.assertEqual(fields['문구 구분'].text(),'자금이체')
                with patch.object(q.filedialog,'askopenfilename',return_value=str(DATABASE.parent/'originals'/'원본.xls')):buttons['자료 설정'].click()
                wait(lambda:hasattr(window,'_latest_transfer_import') and not window._read_task.busy)
                self.assertEqual(window._latest_transfer_import['accounts'],221)
                self.assertEqual(len(read_accounts(folder/'settings'/'accounts'/'transfer_accounts.sqlite3')),221)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
