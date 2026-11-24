import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PySide6.QtTest import QTest
import qt_ui as tk
import app
from work_records import RecordBook
from work_records_ui import RecordTable


def test_sheet_updates_are_scoped_and_atomic(tmp_path):
    path = tmp_path / 'records.sqlite3'
    book = RecordBook(path)
    first = book.name_task('결산')
    second = book.name_task('세무')
    book.write_cells(first, '업무 흐름', [], 0, [['수집', '자료 취합'], ['대사']])
    rows = book.rows(first, '업무 흐름')
    keys = [row[0] for row in rows]
    with pytest.raises(ValueError):
        book.write_cells(first, '업무 흐름', keys, 3, [['수정'], ['열', '초과']])
    assert book.rows(first, '업무 흐름') == rows
    book.move_row(first, '업무 흐름', keys[1], -1)
    book.write_cells(second, '서류 목록', [], 0, [['신고서']])
    assert not book.rows(second, '업무 흐름')
    assert not book.rows(first, '서류 목록')
    assert RecordBook(path).rows(first, '업무 흐름') == rows[::-1]
    with pytest.raises(ValueError):
        book.name_task('세무', first)
    book.name_task('연말 결산', first)
    book.delete_row(keys[0])
    assert len(book.rows(first, '업무 흐름')) == 1
    book.delete_task(first)
    assert not book.rows(first, '업무 흐름')
    assert book.rows(second, '서류 목록')[0][1] == '신고서'


def test_workspace_open_edit_switch_paste_and_reopen(tmp_path):
    with patch.object(app, 'desktop', return_value=tmp_path), patch.object(tk.Tk, 'mainloop'), \
            patch('startup_update.check_on_start'):
        app.main()
        root = tk._default_root
        try:
            workspace = root._launcher.workspace
            assert [name for name, _ in root._launcher.groups][-2:] == ['5. 통합 작업', '6. 업무 기록']
            workspace.open('g5c0')
            window = workspace.tabs['g5c0']
            table = window._q.findChild(RecordTable)
            tabs = window._q.findChild(tk.W.QTabBar)
            buttons = {b.text(): b for b in window._q.findChildren(tk.W.QPushButton)}
            with patch('work_records_ui.simpledialog.askstring', return_value='월말 결산'):
                buttons['새 업무'].click()
            buttons['행 추가'].click()
            editor = table.viewport().findChild(tk.W.QLineEdit)
            editor.setText('시산표')
            tabs.setCurrentIndex(1)
            assert table.rowCount() == 0
            tk.application().clipboard().setText('자료 수집\t시산표 내려받기\n검산\t차대변 대사')
            QTest.keyClick(table, tk.C.Qt.Key.Key_V, tk.C.Qt.KeyboardModifier.ControlModifier)
            assert table.item(1, 1).text() == '차대변 대사'
            table.setCurrentCell(1, 0, tk.C.QItemSelectionModel.SelectionFlag.ClearAndSelect)
            buttons['위로'].click()
            assert table.item(0, 0).text() == '검산'
            tabs.setCurrentIndex(2)
            table.pasteRequested.emit('지출 인식\t소모품비\t미지급금')
            tabs.setCurrentIndex(3)
            table.pasteRequested.emit('매월 말일\t분개 검토')
            workspace.close_tab()
            workspace.open('g5c0')
            window = workspace.tabs['g5c0']
            table = window._q.findChild(RecordTable)
            tabs = window._q.findChild(tk.W.QTabBar)
            for index, (column, value) in enumerate([(0, '시산표'), (0, '검산'), (2, '미지급금'), (0, '매월 말일')]):
                tabs.setCurrentIndex(index)
                assert table.item(0, column).text() == value
        finally:
            root.destroy()


def test_sheet_sums_ignore_notes_and_isolate_formula_errors():
    from decimal import Decimal
    from work_record_sums import sheet_values

    values = sheet_values([
        ['1,250.5원', '-0.75', '=sum($A$1:B2)', '=SUM(C1, B1)'],
        ['2026-11-24', '', '=SUM(D2)', '=SUM(C2)'],
        ['=SUM(C2)', '=SUM(A99:A999999)', '=SUM(E1)', '=SUM(C3)'],
    ])
    assert values[0, 2] == Decimal('1249.75')
    assert values[0, 3] == Decimal('1249')
    assert [values[key] for key in ((1, 2), (1, 3), (2, 0))] == ['#순환참조!'] * 3
    assert values[2, 1] == 0
    assert values[2, 2] == values[2, 3] == '#REF!'


def test_sum_selection_edit_and_reopen(tmp_path):
    book = RecordBook(tmp_path / 'settings' / '업무 기록.sqlite3')
    task = book.name_task('합계 확인')
    book.write_cells(task, '서류 목록', [], 0, [['1,000', '=SUM(A1:A2)'], ['-1.50', '메모']])
    with patch.object(app, 'desktop', return_value=tmp_path), patch.object(tk.Tk, 'mainloop'), \
            patch('startup_update.check_on_start'):
        app.main()
        root = tk._default_root
        try:
            workspace = root._launcher.workspace
            workspace.open('g5c0')
            window = workspace.tabs['g5c0']
            table = window._q.findChild(RecordTable)
            total = next(label for label in window._q.findChildren(tk.W.QLabel) if label.accessibleName() == '선택 합계')

            def displayed(table, row, col):
                option = tk.W.QStyleOptionViewItem()
                table.itemDelegate().initStyleOption(option, table.model().index(row, col))
                return option.text

            table.setRangeSelected(tk.W.QTableWidgetSelectionRange(0, 0, 1, 0), True)
            assert total.text().endswith('998.5')
            assert displayed(table, 0, 1) == '998.5'
            table.item(1, 0).setText('2,000.25')
            assert total.text().endswith('3,000.25')
            assert displayed(table, 0, 1) == '3,000.25'
            table.setCurrentCell(0, 1)
            table.editItem(table.currentItem())
            editor = table.indexWidget(table.currentIndex())
            assert editor.text() == '=SUM(A1:A2)'
            editor.setText('=SUM(A2)')
            QTest.keyClick(editor, tk.C.Qt.Key.Key_Return)
            tk.application().processEvents()
            assert displayed(table, 0, 1) == '2,000.25'
            workspace.close_tab()
            workspace.open('g5c0')
            table = workspace.tabs['g5c0']._q.findChild(RecordTable)
            assert displayed(table, 0, 1) == '2,000.25'
            assert book.rows(task, '서류 목록')[0][2] == '=SUM(A2)'
        finally:
            root.destroy()
