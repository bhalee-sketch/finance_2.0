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

    def test_background_reads_and_legacy_workers_report_progress_and_cleanup(self):
        from background_read import BackgroundRead
        from loading_ui import watch_loading
        from unittest.mock import patch
        root=q.Tk();root.geometry('800x600');view=q.Toplevel(root);view.geometry('700x500')
        status=q.StringVar(value='처리 중');reader=BackgroundRead(view,status);release=threading.Event();completed=[]
        def wait(predicate):
            end=time.monotonic()+3
            while time.monotonic()<end:
                q.application().processEvents()
                if predicate():return
                time.sleep(.01)
            self.fail('Timed out')
        def visible():return [w for w in view.children.values() if isinstance(w,q.Toplevel) and w.winfo_exists() and w._q.isVisible()]
        try:
            reader.run(lambda:release.wait(3),completed.append,completed.append)
            wait(lambda:bool(visible()));release.set();wait(lambda:bool(completed))
            self.assertFalse(visible())
            state={'busy':True};indicator=watch_loading(view,status,lambda:state['busy'])
            wait(lambda:bool(visible()))
            state['busy']=False;wait(lambda:not visible())
            self.assertFalse(indicator.active)
            def fail():raise ValueError('test failure')
            reader.run(fail,lambda _:self.fail('Unexpected success'),completed.append)
            wait(lambda:len(completed)==2)
            self.assertIsInstance(completed[-1],ValueError);self.assertFalse(visible())
        finally:release.set();root.destroy()

    def test_statement_toolbar_buttons_fit_inside_parent_at_all_scales(self):
        import tempfile
        from statement_ui import open_statement_view
        from appearance import set_appearance
        from unittest.mock import patch
        root=q.Tk();root.geometry('1400x850');root.report_callback_exception=lambda *args:self.fail(str(args))
        try:
            with tempfile.TemporaryDirectory() as folder,patch('statement_database.discover_statements',return_value={}):
                open_statement_view(root,lambda:Path(folder),lambda w,x,y:w.geometry(f'{x}x{y}'),lambda _:None)
                view=next(w for w in root.children.values() if isinstance(w,q.Toplevel))
                for scale in (80,110,150):
                    set_appearance(root,'light',q.font.families()[0],text_scale=scale)
                    deadline=time.monotonic()+.3
                    while time.monotonic()<deadline:q.application().processEvents();time.sleep(.005)
                    buttons=[w for w in view._q.findChildren(q.W.QPushButton) if 'Excel 저장' in w.text() or w.text()=='연도 새로고침']
                    self.assertEqual(len(buttons),3)
                    for button in buttons:
                        self.assertGreaterEqual(button.y(),button.parentWidget().contentsRect().top())
                        self.assertLessEqual(button.geometry().bottom(),button.parentWidget().contentsRect().bottom())
        finally:root.destroy()

if __name__=='__main__':unittest.main()
