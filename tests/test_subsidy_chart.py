import os
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import qt_ui as q
from analysis_charts import draw_curve, grant_bars, million, segment_hits_box
from gov_subsidy import load_bundled_subsidies, subsidy_series


def test_subsidy_amount_labels_clear_drawn_total_line():
    headers, rows = subsidy_series(load_bundled_subsidies()[0])
    rows = [row for row in rows if '2021' <= row[0] <= '2025']
    amounts = sorted(million(value) for _, *values in rows for value in [*values, sum(values)])
    root = q.Tk()
    try:
        for width, height in ((1600, 620), (1100, 460), (900, 390)):
            canvas = q.Canvas(root, width=width, height=height)
            with patch('analysis_charts.draw_curve', wraps=draw_curve) as curve:
                grant_bars(canvas, headers, rows)
            points = curve.call_args.args[1]
            assert len(points) == len(rows)
            segments = list(zip(points, points[1:]))
            labels = canvas.find_withtag('chart_value')
            assert sorted(canvas.itemcget(item, 'text') for item in labels) == amounts
            for item in [*labels, *canvas.find_withtag('chart_value_background')]:
                assert not any(segment_hits_box(seg, canvas.bbox(item)) for seg in segments)
    finally:
        root.destroy()
