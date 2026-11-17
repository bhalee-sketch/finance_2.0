import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qt_ui as q
from PySide6.QtTest import QTest
from appearance import set_appearance
from statement_grid import StatementGrid


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.root = q.Tk()

    def tearDown(self):
        self.root.destroy()

    def test_dropdown_highlight_contrast_after_theme_changes(self):
        # Test both existing and newly created dropdowns under each theme.
        boxes = [q.ttk.Combobox(self.root, values=['전체', '수입', '지출'], state='readonly')]
        for theme in ['light', 'dark', 'light']:
            set_appearance(self.root, theme, q.application().font().family())
            boxes.append(q.ttk.Combobox(self.root, values=['추가 항목'], state='readonly'))
            for box in boxes:
                box.pack()
                box._q.showPopup()
                view = box._q.view()
                view.ensurePolished()
                q.application().processEvents()
                palette = view.palette()
                text = palette.color(q.G.QPalette.ColorRole.HighlightedText)
                background = palette.color(q.G.QPalette.ColorRole.Highlight)
                self.assertEqual(text.name(), '#403b4a' if theme == 'light' else '#eae5f4')
                self.assertNotEqual(text, background)
                box._q.hidePopup()

    def test_statement_headers_never_sort(self):
        table = StatementGrid(self.root, columns=['과목', '금액'], show='headings')
        table.pack(fill='both', expand=True)
        self.root.geometry('800x400')
        for label, amount in [('총계', 300), ('나항목', 200), ('가항목', 100)]:
            table.insert('', 'end', values=[label, amount])
        def order():
            return [table.proxy.index(i, 0).data() for i in range(table.proxy.rowCount())]
        original = order()
        for fitted in [False, True]:
            if fitted:
                table.fit_to_viewport({'0': 300, '1': 150}, 0)
            q.application().processEvents()
            header = table._q.horizontalHeader()
            self.assertFalse(table._q.isSortingEnabled())
            self.assertFalse(header.sectionsClickable())
            self.assertFalse(header.isSortIndicatorShown())
            for column in range(2):
                point = q.C.QPoint(header.sectionViewportPosition(column) + 10, header.height() // 2)
                QTest.mouseClick(header.viewport(), q.C.Qt.MouseButton.LeftButton, pos=point)
                header.sectionClicked.emit(column)
                q.application().processEvents()
                self.assertEqual(order(), original)
                self.assertEqual(table.proxy.sortColumn(), -1)


if __name__ == '__main__':
    unittest.main()
