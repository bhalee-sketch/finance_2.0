import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from decimal import Decimal
import unittest
from types import SimpleNamespace

import qt_ui as q
from analysis_charts import donut, stacked_years
from chart_tooltips import show_tip


class AnalysisChartLayoutTests(unittest.TestCase):
    def test_donut_text_is_centered_and_stacked_values_fit(self):
        root = q.Tk()
        try:
            canvas = q.Canvas(root, width=950, height=500)
            donut(canvas, [('보수', Decimal(29631000000)), ('운영비', Decimal(85428000000))],
                  total_label='자금지출총계')
            for item in self.labels(canvas, '자금지출총계', '115,059백만원'):
                box = canvas.bbox(item)
                self.assertAlmostEqual((box[0] + box[2])/2, canvas.winfo_width()/2, places=1)

            stacked_years(canvas, ['연도', '보수', '운영비', '기타'], [['2025', 65, 30, 5]])
            for index, label in enumerate(('65.0%', '30.0%')):
                item, = self.labels(canvas, label)
                box = canvas.bbox(item)
                tag = f'ratio_0_{index}'
                bar, = [shape for shape in canvas.find_withtag(tag) if canvas.type(shape) == 'rectangle']
                bounds = canvas.bbox(bar)
                self.assertAlmostEqual((box[0] + box[2])/2, (bounds[0] + bounds[2])/2, places=1)
                self.assertGreater(box[1], bounds[1])
                self.assertLess(box[3], bounds[3])
            total, = self.labels(canvas, '100.0%')
            self.assertLess(canvas.bbox(total)[3], 52)
        finally:
            root.destroy()

    def test_hover_box_fits_its_content(self):
        root = q.Tk()
        try:
            canvas = q.Canvas(root, width=950, height=500)
            show_tip(canvas, SimpleNamespace(x=100, y=100), '보수\n29,631백만원 · 25.75%\n29,630,981,807원')
            tip = canvas.bbox('tip')
            self.assertLess(tip[2]-tip[0], 230)
        finally:
            root.destroy()

    def labels(self, canvas, *expected):
        found = [i for i in canvas.find_all()
                 if canvas.type(i) == 'text' and canvas.itemcget(i, 'text') in expected]
        self.assertEqual(len(found), len(expected))
        return found
