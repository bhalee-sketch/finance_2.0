import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest

import qt_ui as q
from rental_ui import CONTRACT_BUTTON_COLUMN, PERIOD_COLUMN, open_rentals
from rental_data import create_rental,load_rentals,update_rental


class RentalLayoutTests(unittest.TestCase):
    def test_contracts_and_forecast_fit_the_window(self):
        record = {
            'group': '대학', 'location': '본관', 'tenant': '테스트',
            'representative': '대표', 'business': '123-45-67890', 'period': '2021-11-11～2027-11-10',
            'deposit': None, 'monthly': 1000, 'annual': 12000, 'term': '월납',
            'number': 1024, 'notes': [], 'start': date(2021, 11, 11), 'end': date(2027, 11, 10),
        }
        root = q.Tk()
        try:
            with patch('rental_ui.load_rentals', return_value=([record], [])), patch.object(q.messagebox, 'showerror') as error:
                open_rentals(root, Path.home, lambda window, *_: window.geometry('1680x750'), lambda path: None)
                window = root.winfo_children()[0]
                tabs = window._q.findChild(q.W.QTabWidget)
                self.assertEqual([tabs.tabText(i) for i in range(tabs.count())], ['현황','만료','월·연 예상 수익'])
                view = tabs.widget(0).findChild(q.W.QTableView)
                for _ in range(150):
                    QTest.qWait(20)
                    if view.model().rowCount() or error.called:
                        break
                error.assert_not_called()
                model = view.model()
                horizontal = q.C.Qt.Orientation.Horizontal
                self.assertEqual([model.headerData(i, horizontal) for i in (0, 1)], ['계약번호', '구분'])
                self.assertEqual(model.index(0, 0).data(), '1024')
                monthly = next(i for i in range(model.columnCount()) if model.headerData(i, horizontal) == '월 환산 임대료')
                self.assertEqual(model.index(1, monthly).data(), '1,000')
                self.assertNotIn('새로고침', [b.text() for b in window._q.findChildren(q.W.QPushButton)])
                index = view.model().index(0, PERIOD_COLUMN)
                self.assertEqual(index.data(), '2021.11.11 ~ 2027.11.10')
                option = q.W.QStyleOptionViewItem()
                self.assertIsNone(view.itemDelegateForColumn(PERIOD_COLUMN))
                view.itemDelegate().initStyleOption(option, index)
                metrics = q.G.QFontMetrics(option.font)
                self.assertEqual(option.font.pointSizeF(), index.data(q.C.Qt.ItemDataRole.FontRole).pointSizeF())
                self.assertGreaterEqual(view.columnWidth(PERIOD_COLUMN), metrics.horizontalAdvance(index.data())+8)

                combos=window._q.findChildren(q.W.QComboBox)
                group_box=next(box for box in combos if box.findText('제네시스랩')>=0)
                year_box=next(box for box in combos if box.accessibleName()=='예상 연도')
                self.assertEqual(year_box.currentText(),str(date.today().year))
                with patch('rental_ui.bars') as draw:
                    for selected,names in [('대학',['대학']),('제네시스랩',['제네시스랩']),('전체',['대학','제네시스랩'])]:
                        group_box.setCurrentText(selected)
                        group_box.activated.emit(group_box.currentIndex())
                        QTest.qWait(40)
                        for call in draw.call_args_list[-2:]:
                            self.assertEqual(call.args[1][1:],names)
                            self.assertEqual(call.kwargs['show_total'],selected=='전체')
                        self.assertGreaterEqual(draw.call_count,2)
                        draw.reset_mock()

                QTest.qWait(80)
                button = next(button for button in view.findChildren(q.W.QPushButton) if button.text() == '계약서 보기')
                self.assertTrue(button.isVisible())
                self.assertEqual(button.cursor().shape(), q.C.Qt.CursorShape.PointingHandCursor)
                center = button.mapTo(view.viewport(), button.rect().center())
                self.assertEqual(view.indexAt(center).column(), CONTRACT_BUTTON_COLUMN)
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

                    tabs.setCurrentIndex(2)
                    QTest.qWait(80)
                    self.assertEqual(window._scroll.horizontalScrollBar().maximum(), 0)
                    charts = [chart for chart in tabs.currentWidget().findChildren(q.W.QGraphicsView) if chart.isVisible()]
                    self.assertEqual(len(charts), 2)
                    for chart in charts:
                        self.assertLessEqual(chart.mapTo(window._q, chart.rect().topRight()).x(), width)
        finally:
            root.destroy()

    def test_confirm_exit_moves_contract_and_opens_archived_pdf(self):
        with TemporaryDirectory() as tmp:
            desktop=Path(tmp);settings=desktop/'settings';folder=settings/'contract'
            create_rental(folder,'대학',{'tenant':'업체','period':'2025-01-01 ~ 2027-12-31'})
            pdf=folder/'campus'/'1. 계약서.pdf'
            pdf.parent.mkdir();pdf.write_bytes(b'test')
            opened=[]
            root=q.Tk()
            try:
                open_rentals(root,lambda:desktop,lambda w,*_:w.geometry('1280x850'),opened.append)
                window=root.winfo_children()[0]
                tabs=window._q.findChild(q.W.QTabWidget)
                current=tabs.widget(0).findChild(q.W.QTableView)
                expired=tabs.widget(1).findChild(q.W.QTableView)
                def wait(predicate):
                    for _ in range(150):
                        if predicate():return
                        QTest.qWait(20)
                    self.fail('임대사항 화면 갱신 시간 초과')
                wait(lambda:current.model().rowCount()==2)
                point=current.visualRect(current.model().index(0,0)).center()
                QTest.mouseDClick(current.viewport(),q.C.Qt.MouseButton.LeftButton,pos=point)
                dialog=next(w for w in window.winfo_children() if isinstance(w,q.Toplevel))
                field=next(w for w in dialog._q.findChildren(q.W.QLineEdit) if w.accessibleName()=='퇴거일')
                field.setText('2026-10-01')
                button=next(w for w in dialog._q.findChildren(q.W.QPushButton) if w.text()=='원자료에 저장')
                with patch.object(q.messagebox,'askyesno',side_effect=[False,True]) as confirm:
                    button.click()
                    self.assertIsNone(load_rentals(folder)[0][0]['exited'])
                    self.assertTrue(pdf.is_file())
                    button.click()
                self.assertEqual(confirm.call_count,2)
                wait(lambda:tabs.currentIndex()==1 and expired.model().rowCount()==2)
                self.assertEqual(current.model().rowCount(),1)
                self.assertEqual(load_rentals(folder)[0][0]['exited'],date(2026,10,1))
                self.assertFalse(pdf.exists())
                open_pdf=next(b for b in expired.findChildren(q.W.QPushButton) if b.text()=='계약서 보기')
                wait(open_pdf.isVisible)
                QTest.mouseClick(open_pdf,q.C.Qt.MouseButton.LeftButton)
                self.assertEqual(opened,[settings/'contract-expried'/'campus'/pdf.name])
            finally:root.destroy()

    def test_locked_workbook_restores_pdfs_and_preserves_existing_archive(self):
        with TemporaryDirectory() as tmp:
            settings=Path(tmp);folder=settings/'contract'
            result=create_rental(folder,'대학',{'tenant':'업체','period':'2025-01-01 ~ 2027-12-31'})
            record=load_rentals(folder)[0][0]
            pdf=folder/'campus'/'1. 계약서.pdf';pdf.parent.mkdir();pdf.write_bytes(b'current')
            old=settings/'contract-expried'/'campus'/pdf.name
            old.parent.mkdir(parents=True);old.write_bytes(b'archived')
            original_replace=os.replace
            def locked(source,target):
                if Path(target)==result['path']:raise PermissionError('열린 원자료')
                return original_replace(source,target)
            with patch('os.replace',side_effect=locked),self.assertRaises(PermissionError):
                update_rental(record,{'exited':'2026-10-01'})
            self.assertIsNone(load_rentals(folder)[0][0]['exited'])
            self.assertEqual(pdf.read_bytes(),b'current')
            self.assertEqual(old.read_bytes(),b'archived')
            self.assertEqual(list(old.parent.iterdir()),[old])
