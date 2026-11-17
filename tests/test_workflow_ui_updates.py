import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from openpyxl import Workbook,load_workbook
from statement_appendix import _verify_by_mapping
from statement_ui import export_appendix
from launcher import Launcher

class UpdatesTests(unittest.TestCase):
    def test_blank_amount_zero_and_missing_sheet(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'supp.xlsx';book=Workbook();book.active.title='명세서';book.save(p);book.close()
            result=_verify_by_mapping({'빈계정':None,'차이계정':10},str(p),
                {'빈계정':('명세서','A1'),'차이계정':('명세서','A1'),'없는시트':('없음','A1')},'검증')
            self.assertEqual((result[0]['fs_amount'],result[0]['supp_amount']),(0,0))
            self.assertTrue(result[0]['is_match'])
            self.assertEqual(result[1]['diff'],10)
            self.assertFalse(result[1]['is_match'])
            self.assertFalse(result[2]['is_match'])
            report={'items':result,'total':3,'matched':1,'mismatched':2}
            target=export_appendix(report,Path(folder)/'out.xlsx');book=load_workbook(target)
            self.assertEqual(book.active['F3'].value,'확인필요')
            self.assertEqual(book.active['A3'].fill.fgColor.rgb[-6:],'FDE8E8')
            self.assertEqual(book.active['C2'].value,0)
            book.close()

    def test_top_tabs_scroll_without_moving_right_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=q.Tk()
            def open_page():
                w=q.Toplevel(root);q.ttk.Label(w,text='테스트').pack()
            groups=[('분류',[(f'긴 작업 메뉴 {i}',open_page) for i in range(24)])]
            launcher=Launcher(root,groups,Path(folder)/'settings.json')
            root.geometry('1000x700+0+0');q.application().processEvents()
            workspace=launcher.workspace
            before=workspace.local_badge.mapToGlobal(q.C.QPoint(0,0)).x()
            try:
                for key in workspace.commands:
                    workspace.open(key);q.application().processEvents()
                after=workspace.local_badge.mapToGlobal(q.C.QPoint(0,0)).x()
                self.assertLessEqual(abs(after-before),2)
                tabs=workspace.top_tabs
                arrows=[b for b in tabs.findChildren(q.W.QToolButton)
                        if b.arrowType()!=q.C.Qt.ArrowType.NoArrow and b.isVisible()]
                self.assertEqual(len(arrows),2)
                self.assertLess(tabs.mapToGlobal(q.C.QPoint(tabs.width(),0)).x(),after)
                old=tabs.tabRect(0).x()
                next(b for b in arrows if b.arrowType()==q.C.Qt.ArrowType.LeftArrow).click()
                q.application().processEvents()
                self.assertNotEqual(tabs.tabRect(0).x(),old)
            finally:root.destroy()

if __name__=='__main__':unittest.main()
