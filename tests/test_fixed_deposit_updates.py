import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,sqlite3,tempfile,time,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
import qt_ui as q
from fixed_deposit_database import normalize_source,import_fixed_accounts,load_fixed_accounts,DATABASE
from deposit_accounts import load_accounts
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

    def test_add_replace_and_sort_account_catalogs(self):
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
                footer=next(w for w in window._q.findChildren(q.W.QLabel)
                            if w.text()=='계좌와 금액을 입력하고 목록에 추가하세요.')
                self.assertGreaterEqual(footer.height(),footer.fontMetrics().height())
                self.assertLessEqual(footer.mapTo(window._q,footer.rect().bottomLeft()).y(),window._q.rect().bottom())
                buttons={w.text():w for w in window._q.findChildren(q.W.QPushButton)}
                self.assertNotIn('계좌 새로고침',buttons)
                self.assertEqual(sum('계획표 생성' in name for name in buttons),1)
                self.assertIs(buttons['계좌 추가'].parentWidget(),buttons['계획표 생성'].parentWidget())
                self.assertLess(buttons['계좌 추가'].x(),buttons['계획표 생성'].x())

                def account_dialog(regular=False):
                    buttons['계좌 추가'].click()
                    dialog=next(w for w in window.winfo_children() if isinstance(w,q.Toplevel) and w.title()=='계좌 추가')
                    if regular:
                        box=next(w for w in dialog._q.findChildren(q.W.QComboBox) if w.accessibleName()=='계좌 종류')
                        box.setCurrentIndex(1);box.activated.emit(1)
                    return dialog

                def add_account(number,regular=False):
                    dialog=account_dialog(regular)
                    values={'계좌번호':number,'은행명':'테스트은행','계좌명':'신규계좌','회계단위':'교비','원금':'10,000'}
                    for entry in dialog._q.findChildren(q.W.QLineEdit):
                        entry.setText(values[entry.accessibleName()])
                    next(w for w in dialog._q.findChildren(q.W.QPushButton) if w.text()=='추가').click()
                    wait(lambda:not window._read_task.busy)

                def upload_accounts(source,regular=False):
                    dialog=account_dialog(regular)
                    with patch.object(q.filedialog,'askopenfilename',return_value=str(source)), \
                         patch.object(q.messagebox,'askyesno',return_value=True):
                        next(w for w in dialog._q.findChildren(q.W.QPushButton) if w.text()=='Excel 업로드로 목록 교체').click()
                    wait(lambda:not window._read_task.busy)

                def choices(name):
                    box=next(w for w in window._q.findChildren(q.W.QComboBox) if w.accessibleName()==name)
                    return [box.itemText(i) for i in range(box.count())]

                local=folder/'settings'/'deposit plan'
                add_account('000-01')
                self.assertEqual(load_fixed_accounts(local/'fixed_accounts.sqlite3')['00001']['principal'],10000)
                self.assertTrue(choices('출금할 정기예금 계좌')[0].startswith('000-01'))
                add_account('000-02',regular=True)
                self.assertIn('00002',load_accounts(local/'regular_accounts.sqlite3'))
                self.assertTrue(choices('원금 이체 계좌')[0].startswith('000-02'))
                self.assertTrue(choices('이자 이체 계좌')[1].startswith('000-02'))

                upload_accounts(DATABASE.parent/'originals'/'원본 FIXED.xls')
                self.assertEqual(window._latest_fixed_import['accounts'],75)
                self.assertNotIn('00001',load_fixed_accounts(local/'fixed_accounts.sqlite3'))
                source=folder/'transfer.xlsx'
                book=Workbook();sheet=book.active
                sheet.append(['계좌번호','은행명','계좌명'])
                sheet.append(['005-01','테스트은행','대체 계좌'])
                book.save(source);book.close()
                upload_accounts(source,regular=True)
                self.assertEqual(list(load_accounts(local/'regular_accounts.sqlite3')),['00501'])
                self.assertEqual(len(choices('원금 이체 계좌')),1)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
