import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from launcher import Launcher

class WindowCreationTests(unittest.TestCase):
    def test_no_standalone_flash_before_tab(self):
        root=q.Tk();seen=[]
        class Observer(q.C.QObject):
            def eventFilter(self,obj,event):
                if event.type()==q.C.QEvent.Type.Show and isinstance(obj,q.W.QWidget):
                    if obj.isWindow() and obj.windowTitle()=='업무' and not obj.testAttribute(q.C.Qt.WidgetAttribute.WA_DontShowOnScreen):
                        seen.append(obj)
                return False
        observer=Observer();q.application().installEventFilter(observer)
        def workflow():
            window=q.Toplevel(root);window.title('업무')
            window.deiconify();q.application().processEvents()
            window.after_idle(window._q.show)
        try:
            with tempfile.TemporaryDirectory() as folder:
                launcher=Launcher(root,[('분류',[('업무',workflow)])],Path(folder)/'settings.json')
                workspace=launcher.workspace;workspace.open('g0c0')
                q.application().processEvents()
                window=workspace.tabs['g0c0']
                self.assertFalse(seen)
                self.assertFalse(window._q.isWindow())
                self.assertFalse(window._q.testAttribute(q.C.Qt.WidgetAttribute.WA_DontShowOnScreen))
                self.assertTrue(window._q.isVisible())
                workspace.open('g0c0');self.assertEqual(len(workspace.tabs),1)
                # Regular dialogs opened outside menu creation remain normal windows.
                dialog=q.Toplevel(window);self.assertTrue(dialog._q.isWindow())
                self.assertFalse(dialog._q.testAttribute(q.C.Qt.WidgetAttribute.WA_DontShowOnScreen))
                dialog.destroy()
        finally:
            q.application().removeEventFilter(observer);root.destroy()

if __name__=='__main__':unittest.main()
