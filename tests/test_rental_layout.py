import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest

import qt_ui as q
from rental_ui import PERIOD_COLUMN, open_rentals


class RentalLayoutTests(unittest.TestCase):
    def test_contracts_and_forecast_fit_the_window(self):
        record = {
            'group': '대학', 'location': '본관', 'tenant': '테스트',
            'representative': '대표', 'business': '123-45-67890', 'period': '2021-11-11～2027-11-10',
            'deposit': None, 'monthly': 1000, 'annual': 12000, 'term': '월납',
            'number': 1, 'notes': [], 'start': date(2021, 11, 11), 'end': date(2027, 11, 10),
        }
        root = q.Tk()
        try:
            with patch('rental_ui.load_rentals', return_value=([record], [])), patch.object(q.messagebox, 'showerror') as error:
                open_rentals(root, Path.home, lambda window, *_: window.geometry('1680x750'), lambda path: None)
                window = root.winfo_children()[0]
                view = window._q.findChild(q.W.QTableView)
                for _ in range(150):
                    QTest.qWait(20)
                    if view.model().rowCount() or error.called:
                        break
                error.assert_not_called()
                index = view.model().index(0, PERIOD_COLUMN)
                self.assertEqual(index.data(), '2021.11.11 ~ 2027.11.10')
                option = q.W.QStyleOptionViewItem()
                self.assertIsNone(view.itemDelegateForColumn(PERIOD_COLUMN))
                view.itemDelegate().initStyleOption(option, index)
                metrics = q.G.QFontMetrics(option.font)
                self.assertEqual(option.font.pointSizeF(), index.data(q.C.Qt.ItemDataRole.FontRole).pointSizeF())
                self.assertGreaterEqual(view.columnWidth(PERIOD_COLUMN), metrics.horizontalAdvance(index.data())+8)

                QTest.qWait(80)
                button = next(button for button in view.findChildren(q.W.QPushButton) if button.text() == '계약서 보기')
                self.assertTrue(button.isVisible())
                self.assertLessEqual(button.width(), 72)
                self.assertLessEqual(button.height(), 22)
                tabs = window._q.findChild(q.W.QTabWidget)
                for width in (1680, 1024, 760):
                    window.geometry(f'{width}x750')
                    tabs.setCurrentIndex(0)
                    QTest.qWait(80)
                    self.assertLessEqual(view.horizontalHeader().length(), view.viewport().width())
                    self.assertEqual(view.horizontalScrollBar().maximum(), 0)
                    self.assertEqual(window._scroll.horizontalScrollBar().maximum(), 0)

                    tabs.setCurrentIndex(1)
                    QTest.qWait(80)
                    self.assertEqual(window._scroll.horizontalScrollBar().maximum(), 0)
                    charts = [chart for chart in tabs.currentWidget().findChildren(q.W.QGraphicsView) if chart.isVisible()]
                    self.assertEqual(len(charts), 2)
                    for chart in charts:
                        self.assertLessEqual(chart.mapTo(window._q, chart.rect().topRight()).x(), width)
        finally:
            root.destroy()
