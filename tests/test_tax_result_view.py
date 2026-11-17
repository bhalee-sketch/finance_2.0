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
            self.assertEqual([len(s['rows']) for s in sheets],[2,0])
            stack.enter_context(patch.object(app,'desktop',return_value=folder))
            stack.enter_context(patch('result_paths.desktop_dir',return_value=folder))
            stack.enter_context(patch('startup_update.check_on_start'))
            stack.enter_context(patch.object(q.Tk,'mainloop'))
            stack.enter_context(patch.object(app,'open_result_file'))
            runner=stack.enter_context(patch.object(app,'run',return_value=output))
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
                self.assertIs(boxes['검증 구분'].parent(),button.parent())
                self.assertLess(boxes['검증 구분'].width(),240)
                self.assertLess(boxes['검증 월·기간'].width(),180)
                button.click();end=time.monotonic()+5
                while time.monotonic()<end:
                    q.application().processEvents()
                    if errors:self.fail(str(errors))
                    if window._tax_results.tabs.count()==2:break
                    time.sleep(.01)
                self.assertEqual(window._tax_results.tabs.count(),2)
                self.assertEqual(len(window._tax_results.tree.get_children()),2)
                self.assertIn('2건',window._work_status.get())
                self.assertEqual(runner.call_args.args[1],(1,))
                window._tax_results.tabs.setCurrentIndex(1);q.application().processEvents()
                self.assertFalse(window._tax_results.tree.get_children())
                self.assertIn('차이가 없습니다',window._tax_results.note.get())
            finally:root.destroy()

if __name__=='__main__':unittest.main()
