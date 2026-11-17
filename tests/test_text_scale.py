import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from launcher import Launcher,load_preferences


class TextScaleTests(unittest.TestCase):
    def test_independent_pt_preview_save_reopen_cancel(self):
        root=q.Tk()
        def pump():
            end=time.monotonic()+.2
            while time.monotonic()<end:q.application().processEvents();time.sleep(.005)
        def click(window,text):
            next(b for b in window._q.findChildren(q.W.QPushButton) if b.text()==text).click();pump()
        def controls(window):return {w.accessibleName():w for w in window._q.findChildren(q.W.QDoubleSpinBox)}
        try:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'settings.json';launcher=Launcher(root,[],path)
                launcher.customize();window=launcher.settings_window;spins=controls(window)
                self.assertFalse(window._q.findChildren(q.W.QSlider))
                self.assertEqual(set(spins),{'투명도','메뉴 크기','시스템 제목 및 메뉴','메뉴 안 설명','실제 데이터'})
                spins['시스템 제목 및 메뉴'].setValue(14);spins['메뉴 안 설명'].setValue(10);spins['실제 데이터'].setValue(16);pump()
                self.assertEqual(launcher.preferences['text_sizes'],{'system':14,'description':10,'data':16})
                label=q.ttk.Label(root,text='설명');label.pack()
                menu=q.ttk.Button(root,text='메뉴');menu.pack()
                tree=q.ttk.Treeview(root,columns=['값']);tree.pack();tree.insert('','end',values=['데이터'])
                pump()
                self.assertAlmostEqual(label._q.font().pointSizeF(),10,delta=.1)
                self.assertAlmostEqual(menu._q.font().pointSizeF(),14,delta=.1)
                self.assertAlmostEqual(tree.proxy.index(0,0).data(q.C.Qt.ItemDataRole.FontRole).pointSizeF(),16,delta=.1)
                spins['메뉴 안 설명'].setValue(9);pump();spins['메뉴 안 설명'].setValue(10);pump()
                self.assertAlmostEqual(menu._q.font().pointSizeF(),14,delta=.1)
                click(window,'저장');self.assertEqual(load_preferences(path)['text_sizes']['data'],16)
                launcher.customize();window=launcher.settings_window;spins=controls(window)
                self.assertEqual(spins['실제 데이터'].value(),16)
                spins['실제 데이터'].setValue(12);pump();click(window,'취소')
                self.assertEqual(launcher.preferences['text_sizes']['data'],16)
                self.assertAlmostEqual(tree.proxy.index(0,0).data(q.C.Qt.ItemDataRole.FontRole).pointSizeF(),16,delta=.1)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
