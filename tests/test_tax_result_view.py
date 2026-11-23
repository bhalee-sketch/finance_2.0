import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,time,unittest
from unittest.mock import patch
from contextlib import ExitStack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
import qt_ui as q
import app
from tax_result_view import read_issue_sheets

class TaxResultTests(unittest.TestCase):
    def test_verify_in_memory_does_not_request_output_path(self):
        from verifier import run,KINDS
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);month=root/'1월';month.mkdir()
            for kind in KINDS:
                for home in (True,False):
                    book=Workbook();sheet=book.active
                    if home:
                        sheet.append(['자료']);sheet.cell(10,2,'123-45-67890');sheet.cell(10,3,'업체')
                        for column,value in ((5,100),(6,10),(7,110)):sheet.cell(10,column,value)
                    else:
                        sheet.append(['사업자번호','거래처명'])
                        sheet.append(['1234567890','업체',None,None,None,100,10,110 if '세금' in kind else 100])
                    book.save(month/f'{"홈택스" if home else "학사"}_{kind}.xlsx');book.close()
            before=set(root.rglob('*.xlsx'))
            with patch('verifier.result_path',side_effect=AssertionError('Unexpected saving')):
                result=run(root,(1,),'test',save=False)
            try:
                self.assertEqual(len(result.sheetnames),5)
                self.assertTrue(all(not sheet['rows'] for sheet in read_issue_sheets(result)))
                self.assertEqual(set(root.rglob('*.xlsx')),before)
            finally:result.close()

    def test_filter_and_embedded_result_after_verification(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            folder=Path(folder);output=folder/'result.xlsx';book=Workbook();book.active.title='검증요약'
            headers=['상태','사업자번호HT','상호_HT','공급가액차이','금액검증']
            sheet=book.create_sheet('01월_매입세금');sheet.append(headers)
            sheet.append(['양쪽','001','정상업체',0,'정상'])
            sheet.append(['양쪽','002','차이업체',100,'차이'])
            sheet.append(['홈택스만','003','단독업체',0,'정상'])
            sheet=book.create_sheet('01월_매출세금');sheet.append(headers);sheet.append(['양쪽','004','정상업체',0,'정상'])
            book.save(output);book.close()
            sheets=read_issue_sheets(output)
            self.assertEqual([len(s['rows']) for s in sheets],[1,0])
            stack.enter_context(patch.object(app,'desktop',return_value=folder))
            stack.enter_context(patch('result_paths.desktop_dir',return_value=folder))
            stack.enter_context(patch('startup_update.check_on_start'))
            stack.enter_context(patch.object(q.Tk,'mainloop'))
            opener=stack.enter_context(patch.object(app,'open_result_file'))
            from openpyxl import load_workbook
            memory_book=load_workbook(output)
            runner=stack.enter_context(patch('verifier.run',return_value=memory_book))
            app.main();root=q._default_root;errors=[]
            root.report_callback_exception=lambda *a:errors.append(str(a))
            try:
                workspace=root._launcher.workspace;workspace.open('g2c0');window=workspace.tabs['g2c0']
                q.application().processEvents()
                button=next(b for b in window._q.findChildren(q.W.QPushButton) if b.text()=='검증 실행')
                offset=next(b for b in window._q.findChildren(q.W.QPushButton) if b.text()=='미처리 상계')
                self.assertIs(button.parent(),offset.parent())
                self.assertLess(button.width(),180)
                boxes={b.accessibleName():b for b in window._q.findChildren(q.W.QComboBox) if b.accessibleName()}
                self.assertIs(boxes['검증 구분'].parent(),boxes['검증 연도'].parent())
                self.assertLess(boxes['검증 구분'].width(),240)
                self.assertLess(boxes['검증 월·기간'].width(),180)
                for text,name in [('검증 연도','검증 연도'),('검증','검증 구분'),('월·기간','검증 월·기간')]:
                    label=next(w for w in window._q.findChildren(q.W.QLabel) if w.text()==text)
                    label_y=label.mapToGlobal(label.rect().center()).y()
                    control=boxes[name]
                    self.assertLessEqual(abs(label_y-control.mapToGlobal(control.rect().center()).y()),2)
                downloads=next(b for b in window._q.findChildren(q.W.QPushButton) if b.text()=='홈택스 자료 내려받기')
                self.assertIs(downloads.parent(),boxes['검증 월·기간'].parent())
                button.click();end=time.monotonic()+5
                while time.monotonic()<end:
                    q.application().processEvents()
                    if errors:self.fail(str(errors))
                    if window._tax_results.tabs.count()==2:break
                    time.sleep(.01)
                self.assertEqual(window._tax_results.tabs.count(),2)
                self.assertEqual(len(window._tax_results.tree.get_children()),1)
                self.assertIn('1건',window._work_status.get())
                opener.assert_not_called()
                self.assertFalse(list((folder/'검증결과').glob('*.xlsx')))
                self.assertEqual(runner.call_args.kwargs,{'save':False})
                excel=next(b for b in window._q.findChildren(q.W.QPushButton) if b.text()=='엑셀로 열기')
                self.assertIs(excel.parent(),button.parent())
                excel.click()
                deadline=time.monotonic()+5
                while not opener.called and time.monotonic()<deadline:
                    q.application().processEvents();time.sleep(.01)
                opener.assert_called_once()
                self.assertTrue(Path(opener.call_args.args[0]).is_file())
                self.assertEqual(window._tax_results.tree._q.horizontalScrollBarPolicy(),q.C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                q.application().processEvents()
                widths=sum(window._tax_results.tree._q.columnWidth(i) for i in range(5))
                self.assertEqual(widths,window._tax_results.tree._q.viewport().width())
                self.assertEqual(runner.call_args.args[1],(1,))
                window._tax_results.tabs.setCurrentIndex(1);q.application().processEvents()
                self.assertFalse(window._tax_results.tree.get_children())
                self.assertIn('차이가 없습니다',window._tax_results.note.get())
            finally:root.destroy()

if __name__=='__main__':unittest.main()
