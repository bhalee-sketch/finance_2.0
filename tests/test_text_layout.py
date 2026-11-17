import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from appearance import set_appearance
from hometax_ui import open_hometax

class TextLayoutTests(unittest.TestCase):
    def test_wrap_width_and_korean_fallback(self):
        root=q.Tk();root.geometry('900x600')
        try:
            set_appearance(root,'light',q.font.families()[0])
            text='한글 표시 확인 ㅡ 으 를 크 로그인 자료 받기 '
            label=q.ttk.Label(root,text=text*5,wraplength=800);label.pack(fill='x')
            q.application().processEvents()
            self.assertEqual(label._q.sizeHint().width(),800)
            self.assertGreaterEqual(label._q.height(),label._q.heightForWidth(label._q.width()))
            self.assertGreater(label._q.heightForWidth(200),label._q.heightForWidth(800))
            layout=q.G.QTextLayout('ㅡ',label._q.font())
            layout.beginLayout();layout.createLine();layout.endLayout()
            runs=layout.glyphRuns()
            self.assertTrue(runs)
            self.assertTrue(all(0 not in run.glyphIndexes() for run in runs))
        finally:root.destroy()

    def test_hometax_window_minimum_and_text_height(self):
        root=q.Tk()
        try:
            with tempfile.TemporaryDirectory() as folder:
                open_hometax(root,Path(folder),'2025',10,
                    lambda w,x,y:w.geometry(f'{x}x{y}'),lambda *a:None)
                q.application().processEvents()
                window=next(w for w in root.children.values() if isinstance(w,q.Toplevel))
                self.assertGreaterEqual(window._q.width(),860)
                self.assertGreaterEqual(window._q.height(),620)
                labels=[w for w in window._q.findChildren(q.W.QLabel) if w.wordWrap() and w.text()]
                for label in labels:
                    self.assertGreaterEqual(label.height(),label.heightForWidth(label.width()),label.text())
        finally:root.destroy()

if __name__=='__main__':unittest.main()
