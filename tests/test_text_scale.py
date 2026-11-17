import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,time,tempfile,unittest,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from launcher import Launcher,load_preferences

class TextScaleTests(unittest.TestCase):
    def test_preview_save_reopen_cancel(self):
        root=q.Tk()
        def pump():
            end=time.monotonic()+.2
            while time.monotonic()<end:q.application().processEvents();time.sleep(.005)
        def click(window,text):
            next(b for b in window._q.findChildren(q.W.QPushButton) if b.text()==text).click();pump()
        try:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'settings.json';launcher=Launcher(root,[],path)
                launcher.customize();window=launcher.settings_window
                slider=next(w for w in window._q.findChildren(q.W.QSlider) if w.accessibleName()=='텍스트 크기')
                slider.setValue(140);pump()
                self.assertEqual(launcher.preferences['text_scale'],140)
                label=q.ttk.Label(root,text='글자',font=('sans-serif',10));label.pack()
                self.assertAlmostEqual(label._q.font().pointSizeF(),14,delta=.1)
                # Repeated changes must not compound the scaling.
                slider.setValue(100);pump();slider.setValue(140);pump()
                self.assertAlmostEqual(label._q.font().pointSizeF(),14,delta=.1)
                click(window,'저장');self.assertEqual(load_preferences(path)['text_scale'],140)
                launcher.customize();window=launcher.settings_window
                slider=next(w for w in window._q.findChildren(q.W.QSlider) if w.accessibleName()=='텍스트 크기')
                self.assertEqual(slider.value(),140)
                slider.setValue(90);pump();click(window,'취소')
                self.assertEqual(launcher.preferences['text_scale'],140)
                self.assertAlmostEqual(label._q.font().pointSizeF(),14,delta=.1)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
