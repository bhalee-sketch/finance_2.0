import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,time,unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from openpyxl import Workbook,load_workbook
from account_ui import open_account_view

class AccountFileTests(unittest.TestCase):
    def test_only_two_files_and_separate_excel_export(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);cms=folder/'cms.xlsx';school=folder/'school.xlsx'
            book=Workbook();sheet=book.active
            sheet.append(['은행',None,None,'계좌번호',None,None,None,'전일','입금','출금','현재잔액'])
            for account,value in [('001',100),('002',90),('003',20)]:
                sheet.append([None,None,None,account,None,None,None,value,0,0,value])
            book.save(cms);book.close()
            book=Workbook();sheet=book.active;sheet.append(['은행','구분','계좌번호','전일잔액','입금','출금'])
            sheet.append([None,None,'001',100,0,0]);sheet.append([None,None,'002',80,0,0])
            book.save(school);book.close()
            originals=(cms.read_bytes(),school.read_bytes())
            root=q.Tk();opener=Mock();errors=[];root.report_callback_exception=lambda *a:errors.append(str(a))
            try:
                window=open_account_view(root,lambda w,x,y:w.geometry(f'{x}x{y}'),opener)
                q.application().processEvents()
                buttons=window._q.findChildren(q.W.QPushButton)
                names=[button.text() for button in buttons]
                self.assertEqual(names.count('파일 선택'),2)
                self.assertFalse(any('폴더' in name for name in names))
                selectors=[button for button in buttons if button.text()=='파일 선택']
                for button,path in zip(selectors,[cms,school]):
                    with patch.object(q.filedialog,'askopenfilename',return_value=str(path)):button.click()
                for entry in window._q.findChildren(q.W.QLineEdit):self.assertLessEqual(entry.width(),480)
                with patch('account_verifier.dated_folder',side_effect=AssertionError('Folder lookup')),patch('account_verifier.find_inputs',side_effect=AssertionError('Auto search')),patch('account_verifier.result_path',side_effect=AssertionError('Auto save')):
                    next(button for button in buttons if button.text()=='검증 실행').click()
                    end=time.monotonic()+5
                    while time.monotonic()<end:
                        q.application().processEvents()
                        if errors:self.fail(str(errors))
                        if window._work_status.get().startswith('검증 완료'):break
                        time.sleep(.01)
                self.assertIn('불일치 2',window._work_status.get())
                view=window._account_results
                self.assertEqual(len(view.tree.get_children()),2)
                self.assertEqual({row[0] for row in view.sheets[0]['rows']},{'002','003'})
                opener.assert_not_called()
                self.assertEqual(set(folder.iterdir()),{cms,school})
                with patch('result_paths.desktop_dir',return_value=folder):
                    next(button for button in buttons if button.text()=='엑셀로 열기').click()
                deadline=time.monotonic()+5
                while not opener.called and time.monotonic()<deadline:
                    q.application().processEvents();time.sleep(.01)
                opener.assert_called_once();output=Path(opener.call_args.args[0]);self.assertTrue(output.exists())
                result=load_workbook(output);self.assertEqual(result['검증결과'].max_row,4);result.close()
                self.assertEqual((cms.read_bytes(),school.read_bytes()),originals)
            finally:root.destroy()

if __name__=='__main__':unittest.main()
