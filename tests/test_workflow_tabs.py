import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import unittest

from PySide6.QtTest import QTest

import qt_ui as q
from ui_theme import qt_stylesheet


class WorkflowTabTests(unittest.TestCase):
    def test_overflow_buttons_use_opposite_edges_and_arrows_select_tabs(self):
        application = q.application()
        previous_style = application.styleSheet()
        application.setStyleSheet(qt_stylesheet())
        root = q.Tk()
        root._q.show()
        try:
            for tabs in (q.WorkflowTabBar(), q.Notebook(root)._q):
                with self.subTest(widget=type(tabs).__name__):
                    bar = tabs if isinstance(tabs, q.W.QTabBar) else tabs.tabBar()
                    try:
                        bar.setExpanding(False)
                        tabs.resize(440, 120)
                        for index in range(12):
                            title = f'비등록금운영비(하나{index:05})'
                            if tabs is bar:
                                bar.addTab(title)
                            else:
                                tabs.addTab(q.W.QWidget(), title)
                        tabs.show()
                        application.processEvents()
                        left = bar.findChild(q.W.QToolButton, 'ScrollLeftButton')
                        right = bar.findChild(q.W.QToolButton, 'ScrollRightButton')
                        self.assertTrue(left.isVisible())
                        self.assertTrue(right.isVisible())
                        self.assertEqual(left.x(), 0)
                        self.assertEqual(right.geometry().right(), bar.rect().right())
                        self.assertFalse(left.isEnabled())
                        self.assertGreaterEqual(bar.tabRect(0).left(), left.width())

                        start = bar.tabRect(0).left()
                        right.click()
                        self.assertLess(bar.tabRect(0).left(), start)
                        left.click()
                        self.assertEqual(bar.tabRect(0).left(), start)

                        bar.setFocus()
                        for _ in range(10):
                            QTest.keyClick(bar, q.C.Qt.Key.Key_Right)
                        self.assertEqual(bar.currentIndex(), 10)
                        self.assertLess(bar.tabRect(10).right(), right.x())
                        QTest.keyClick(bar, q.C.Qt.Key.Key_Left)
                        self.assertEqual(bar.currentIndex(), 9)
                    finally:
                        tabs.close()
        finally:
            root.destroy()
            application.setStyleSheet(previous_style)
