import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,threading,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from statement_ui import Jobs

class LoadingDialogTests(unittest.TestCase):
    def test_dialog_size_center_and_cleanup(self):
        root=q.Tk();root.geometry('750x550+10+10')
        view=q.Toplevel(root);view._q.setWindowFlag(q.C.Qt.WindowType.Window,False)
        view._q.setParent(root._content);view._q.setGeometry(20,30,650,440);view._q.show()
        done=[];release=threading.Event()
        jobs=Jobs(view,q.StringVar())
        jobs.run(lambda:release.wait(5),done.append)
        try:
            end=time.monotonic()+3;loading=None
            while time.monotonic()<end:
                q.application().processEvents()
                loading=next((w for w in view.children.values() if isinstance(w,q.Toplevel)),None)
                if loading and loading._q.isVisible():break
                time.sleep(.01)
            self.assertIsNotNone(loading)
            self.assertLess(loading._q.width(),650)
            self.assertLess(loading._q.height(),300)
            center=view._q.mapToGlobal(view._q.rect().center())
            actual=loading._q.geometry().center()
            self.assertLess(abs(actual.x()-center.x()),5)
            self.assertLess(abs(actual.y()-center.y()),5)
            release.set();end=time.monotonic()+3
            while not done and time.monotonic()<end:
                q.application().processEvents();time.sleep(.01)
            self.assertTrue(done)
            self.assertFalse(loading.winfo_exists())
        finally:
            release.set();root.destroy()

if __name__=='__main__':unittest.main()
