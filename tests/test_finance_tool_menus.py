import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,time,unittest
from unittest.mock import patch
from contextlib import ExitStack
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
import app
from openpyxl import Workbook

class FinanceToolMenuTests(unittest.TestCase):
    def test_real_tools_and_requested_titles(self):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            folder=Path(folder);(folder/'settings').mkdir()
            book=Workbook();book.active.append(['회계단위','계좌명']);book.active.append(['교비','테스트계좌'])
            book.save(folder/'settings'/'accountsforfinancecode.xlsx');book.close()
            stack.enter_context(patch.object(app,'desktop',return_value=folder))
            stack.enter_context(patch('result_paths.desktop_dir',return_value=folder))
            stack.enter_context(patch('startup_update.check_on_start'))
            stack.enter_context(patch.object(q.Tk,'mainloop'))
            app.main();root=q._default_root;errors=[]
            root.report_callback_exception=lambda *a:errors.append(str(a))
            try:
                launcher=root._launcher
                groups=dict(launcher.groups)
                self.assertEqual([name for name,_ in groups['4. 재원·계좌 검증']],['지출계좌별 재원코드','기부금계좌별 잔액','임의기금 재원별 지출내역'])
                self.assertEqual([name for name,_ in groups['5. 통합 작업']],['원장통합','재무제표 Excel 통합','기타작업'])
                workspace=launcher.workspace
                for key,(title,_) in workspace.commands.items():
                    if not key.startswith(('g3','g4')):continue
                    workspace.open(key);end=time.monotonic()+.15
                    while time.monotonic()<end:q.application().processEvents();time.sleep(.005)
                    window=workspace.tabs[key]
                    self.assertEqual(window.title(),title)
                    self.assertTrue(window._q.findChildren(q.W.QPushButton))
                    self.assertFalse(any(label.text()=='준비 중' for label in window._q.findChildren(q.W.QLabel)))
                self.assertFalse(errors)
            finally:root.destroy()

if __name__=='__main__':unittest.main()
