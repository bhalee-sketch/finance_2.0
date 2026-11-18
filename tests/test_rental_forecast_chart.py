import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from decimal import Decimal
import unittest
from unittest.mock import patch

import qt_ui as q
from analysis_charts import bars


class RentalForecastChartTests(unittest.TestCase):
    def test_won_chart_has_truncated_amounts_and_total_line(self):
        root = q.Tk()
        try:
            canvas = q.Canvas(root, width=1000, height=420)
            rows = [
                ('1월', Decimal('20321456.8'), Decimal('1845123.8')),
                ('2월', Decimal('22000000.4'), Decimal('2567890.3')),
            ]
            with patch('analysis_charts.bind_tip') as tips, patch('analysis_charts.draw_curve') as line:
                bars(canvas, ['월', '대학', '제네시스랩'], rows, '월 예상 수익',
                     legend_below_title=True, whole_won=True, show_total=True)

            line.assert_called_once()
            _, points, _ = line.call_args.args
            self.assertLess(points[1][1], points[0][1])
            labels = {canvas.itemcget(item, 'text'): item for item in canvas.find_all() if canvas.type(item) == 'text'}
            self.assertIn('월 예상 수익 (원)', labels)
            self.assertIn('20,321,456', labels)
            self.assertIn('1,845,123', labels)
            self.assertIn('22,166,580', labels)
            self.assertFalse(any('백만원' in label for label in labels))
            details = [call.args[2] for call in tips.call_args_list]
            self.assertIn('1월 · 합계\n22,166,580원', details)
            self.assertIn('2월 · 합계\n24,567,890원', details)
            first_bar = tips.call_args_list[0].args[1]
            self.assertLessEqual(canvas.bbox(labels['20,321,456'])[3] + 5, canvas.bbox(first_bar)[1])
        finally:
            root.destroy()

    def test_standard_bar_chart_keeps_million_won_scale(self):
        root = q.Tk()
        try:
            canvas = q.Canvas(root, width=1000, height=420)
            bars(canvas, ['연도', '수익'], [('2026', Decimal('20000000.8'))])
            labels = {canvas.itemcget(item, 'text') for item in canvas.find_all() if canvas.type(item) == 'text'}
            self.assertIn('결산 (백만원)', labels)
            self.assertIn('20', labels)
            self.assertNotIn('합계', labels)
        finally:
            root.destroy()
