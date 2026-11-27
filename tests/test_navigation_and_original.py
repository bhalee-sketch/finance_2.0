import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from PySide6.QtTest import QTest
from launcher import Launcher
from appendix_view import open_appendix_view
from openpyxl import load_workbook


class NavigationTests(unittest.TestCase):
    def test_dashboard_preserves_tabs_and_unsaved_work(self):
        root=q.Tk();busy=True;close_requests=[]
        def first():
            window=q.Toplevel(root);q.ttk.Entry(window).pack()
        def second():
            window=q.Toplevel(root);q.ttk.Label(window,text='작업 중').pack()
            def close():
                close_requests.append(window)
                if not busy:window.destroy()
            window.protocol('WM_DELETE_WINDOW',close)
        try:
            with tempfile.TemporaryDirectory() as folder:
                launcher=Launcher(root,[('1. 재무제표',[('첫째',first),('둘째',second)])],Path(folder)/'settings.json')
                workspace=launcher.workspace
                q.application().processEvents()
                self.assertLessEqual(workspace.notebook._q.x()-workspace.side.geometry().right()-1,4)
                group=workspace.nav._nodes['g0'];self.assertEqual(group.text(),'재무제표');self.assertFalse(group.icon().isNull())
                workspace.open('g0c0');workspace.open('g0c1');q.application().processEvents()
                opened=workspace.tabs.copy()
                entry=opened['g0c0']._q.findChild(q.W.QLineEdit)
                entry.setText('작성 중')
                self.assertEqual(workspace.home_button.text(),'대시보드')
                workspace.home_button.click();workspace.home_button.click()
                self.assertEqual(workspace.notebook.select(),str(workspace.home))
                self.assertTrue(workspace.home_button.isChecked())
                self.assertEqual(workspace.status.get(),'대시보드')
                busy=False;QTest.qWait(300)
                self.assertEqual(close_requests,[])
                self.assertEqual(workspace.tabs,opened)
                self.assertEqual(workspace.top_tabs.count(),2)
                for index,key in [(1,'g0c1'),(0,'g0c0')]:
                    QTest.mouseClick(workspace.top_tabs,q.C.Qt.MouseButton.LeftButton,
                                     pos=workspace.top_tabs.tabRect(index).center())
                    self.assertEqual(workspace.notebook.select(),str(opened[key]))
                self.assertEqual(entry.text(),'작성 중')
                workspace.close_index(1)
                self.assertEqual(close_requests,[opened['g0c1']])
                self.assertEqual(list(workspace.tabs),['g0c0'])
        finally:root.destroy()

    def test_current_sheet_opens_its_original_workbook_and_year_alignment(self):
        root=q.Tk();opened=[];errors=[];root.report_callback_exception=lambda *args:errors.append(str(args))
        try:
            window=open_appendix_view(root,lambda w,x,y:w.geometry(f'{x}x{y}'),opened.append)
            def ready():
                end=time.monotonic()+10
                while time.monotonic()<end:
                    q.application().processEvents()
                    if errors:self.fail(str(errors))
                    if window._work_status.get().endswith('건'):return
                    time.sleep(.01)
                self.fail('Timed out')
            ready()
            labels=window._q.findChildren(q.W.QLabel)
            self.assertFalse(any(label.text() in ('재무상태표','운영계산서') for label in labels))
            year_label=next(label for label in labels if label.text()=='회계연도');box=window._appendix_year._q
            self.assertLessEqual(abs(year_label.mapToGlobal(year_label.rect().center()).y()-box.mapToGlobal(box.rect().center()).y()),2)
            button=next(button for button in window._q.findChildren(q.W.QPushButton) if button.text()=='현재시트열기')
            for category in ('재무상태표','운영계산서'):
                index=next(i for i,(kind,name) in enumerate(window._appendix_sheet_entries) if kind==category)
                window._appendix_tabs.setCurrentIndex(index);ready();button.click()
                self.assertIn(category,opened[-1].name);self.assertTrue(opened[-1].is_file())
                book=load_workbook(opened[-1],read_only=True)
                try:self.assertIn(window._appendix_sheet_entries[index][1],book.sheetnames)
                finally:book.close()
        finally:root.destroy()

if __name__=='__main__':unittest.main()
