import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from appearance import set_appearance

class HangulRenderingTests(unittest.TestCase):
    def test_thin_stroke_policy_and_rendering(self):
        root=q.Tk()
        try:
            set_appearance(root,'light',q.font.families()[0])
            for size in (9,10,11,12,14):
                font=q.Font(font=('Noto Sans CJK KR',size)).q
                self.assertEqual(font.hintingPreference(),q.G.QFont.HintingPreference.PreferNoHinting)
                self.assertTrue(font.styleStrategy() & q.G.QFont.StyleStrategy.PreferAntialias)
                for ratio in (1,1.25,1.5,2):
                    for text in ('ㅡ','으','크','그','를'):
                        image=q.G.QImage(int(80*ratio),int(50*ratio),q.G.QImage.Format.Format_ARGB32)
                        image.setDevicePixelRatio(ratio);image.fill(q.C.Qt.GlobalColor.white)
                        painter=q.G.QPainter(image);painter.setFont(font);painter.setPen(q.C.Qt.GlobalColor.black)
                        painter.drawText(q.C.QPointF(10,30),text);painter.end()
                        self.assertTrue(any(image.pixelColor(x,y).lightness()<230
                                            for y in range(image.height()) for x in range(image.width())),(size,ratio,text))
            label=q.ttk.Label(root,text='으 크 그 ㅡ')
            self.assertEqual(label._q.font().hintingPreference(),q.G.QFont.HintingPreference.PreferNoHinting)
        finally:root.destroy()

if __name__=='__main__':unittest.main()
