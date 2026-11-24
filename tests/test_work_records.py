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
from work_record_grid import FreeSheet


def test_sheet_updates_are_scoped_and_atomic(tmp_path):
    path = tmp_path / 'records.sqlite3'
    book = RecordBook(path)
    first = book.name_task('결산')
    second = book.name_task('세무')
    book.save_grid(first, {(0, 0): '자료 취합', (2, 3): '=SUM(A1:A2)'})
    book.save_grid(second, {(0, 0): '신고서'})
    with pytest.raises(ValueError):
        book.name_task('세무', first)
    book.name_task('연말 결산', first)
    book.save_grid(first, {(0, 0): ''})
    assert RecordBook(path).grid_values(first) == {(2, 3): '=SUM(A1:A2)'}
    book.delete_task(first)
    assert not book.grid_values(first)
    assert book.grid_values(second) == {(0, 0): '신고서'}


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


def test_existing_notebook_migration_keeps_values_and_formula(tmp_path):
    import sqlite3

    path = tmp_path / 'records.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE tasks (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)')
        db.execute('CREATE TABLE entries (id INTEGER PRIMARY KEY, task INTEGER, section TEXT, position INTEGER, '
                   'value1 TEXT, value2 TEXT, value3 TEXT, value4 TEXT)')
        db.execute("INSERT INTO tasks VALUES (8, '결산')")
        db.execute("INSERT INTO entries VALUES (12, 8, '서류 목록', 1, '10', '=SUM(A1)', '', '')")
    book = RecordBook(path)
    values = book.grid_values(8)
    assert values[0, 0] == '서류명'
    assert values[1, 0] == '10' and values[1, 1] == '=SUM(A2)'
    assert RecordBook(path).grid_values(8) == values


def test_mixed_legacy_task_preserves_coordinates_and_memo(tmp_path):
    import sqlite3

    path = tmp_path / 'records.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, name TEXT UNIQUE, "
                   "format TEXT DEFAULT 'sheet', memo TEXT DEFAULT '')")
        db.execute('INSERT INTO tasks VALUES(1,?,?,?)', ('결산', 'sheet', '=원문\n\n0010'))
        db.execute("INSERT INTO tasks(name) VALUES('결산 · 일정')")
        db.execute('CREATE TABLE entries (id INTEGER PRIMARY KEY, task INTEGER, section TEXT, '
                   'position INTEGER, value1 TEXT, value2 TEXT, value3 TEXT, value4 TEXT)')
        db.execute("INSERT INTO entries VALUES(1,1,'일정',1,'1234','=SUM($A$1)','','')")
        db.execute('CREATE TABLE grid_cells(task INTEGER, row_num INTEGER, col_num INTEGER, value TEXT, '
                   'PRIMARY KEY(task,row_num,col_num))')
        db.execute("INSERT INTO grid_cells VALUES(1,2,0,'=SUM(A1:A2)')")
    book = RecordBook(path)
    tasks = {name: task for task, name in book.tasks()}
    assert book.grid_values(1) == {(2, 0): '=SUM(A1:A2)'}
    assert book.grid_values(tasks['결산 · 일정 (2)'])[1, 1] == '=SUM($A$2)'
    memo_id = tasks['결산 · 메모']
    tk.application()
    grid = FreeSheet(book)
    grid.open_task(memo_id)
    assert grid.model().index(0, 0).data() == '=원문'
    assert grid.model().index(2, 0).data() == '0010'
    book.save_grid(memo_id, {(2, 0): '수정'})
    assert RecordBook(path).grid_values(memo_id)[2, 0] == '수정'
    assert len(book.tasks()) == 4


def test_free_sheet_parallel_tables_formulas_and_reopen(tmp_path):
    with patch.object(app, 'desktop', return_value=tmp_path), patch.object(tk.Tk, 'mainloop'), \
            patch('startup_update.check_on_start'):
        app.main()
        root = tk._default_root
        try:
            workspace = root._launcher.workspace
            workspace.open('g5c0')
            window = workspace.tabs['g5c0']
            button = next(b for b in window._q.findChildren(tk.W.QPushButton) if b.text() == '새 업무')
            with patch('work_records_ui.simpledialog.askstring', return_value='기금 관리'):
                button.click()
            tk.application().processEvents()
            grid = window._q.findChild(FreeSheet)
            model = grid.model()
            selector = window._q.findChild(tk.W.QListWidget, 'WorkRecordTaskList')
            assert selector.currentItem().text() == '기금 관리'
            assert window._q.findChild(tk.W.QTabBar) is None
            assert window._q.findChild(tk.W.QPlainTextEdit) is None
            assert grid.isVisible() and model.headerData(4, tk.C.Qt.Orientation.Horizontal) == 'E'
            grid.setColumnWidth(2, 48)

            def paste(row, col, raw):
                grid.setCurrentIndex(model.index(row, col))
                tk.application().clipboard().setText(raw)
                QTest.keyClick(grid, tk.C.Qt.Key.Key_V, tk.C.Qt.KeyboardModifier.ControlModifier)

            paste(0, 0, '배당 내역\t\t\t장학금 지급 내역')
            grid.setCurrentIndex(model.index(0, 0))
            QTest.keyClick(grid, tk.C.Qt.Key.Key_Right, tk.C.Qt.KeyboardModifier.ShiftModifier)
            merge = next(b for b in window._q.findChildren(tk.W.QPushButton) if b.text() == '셀 병합')
            merge.click()
            assert grid.columnSpan(0, 0) == 2
            assert not model.write({(0, 0): '변경', (0, 1): '겹침'})
            assert model.book.grid_values(model.task)[0, 0] == '배당 내역'
            paste(1, 0, '2019년\t34000000\n2020년\t28000000')
            paste(1, 3, '2019년\t0\n2020년\t10773990')
            paste(9, 1, '=SUM(B2:B9)')
            paste(9, 4, '=SUM(E2:E9)')
            paste(14, 4, '=B10-E10')
            assert model.index(14, 4).data() == '51,226,010'
            paste(4, 5, '123456789012345')
            assert grid.columnWidth(5) >= grid.fontMetrics().horizontalAdvance('123,456,789,012,345') + 6
            assert grid.rowHeight(9) >= grid.verticalHeader().fontMetrics().height() + 6
            paste(1, 1, '35000000')
            assert model.index(14, 4).data() == '52,226,010'
            grid.setCurrentIndex(model.index(1, 1))
            QTest.keyClick(grid, tk.C.Qt.Key.Key_Delete)
            assert model.index(14, 4).data() == '17,226,010'
            paste(19, 25, '다른 업무\t=E15')
            assert model.index(19, 26).data() == '17,226,010'
            grid.setCurrentIndex(model.index(14, 4))
            grid.selectionModel().select(grid.currentIndex(), tk.C.QItemSelectionModel.SelectionFlag.ClearAndSelect)
            QTest.keyClick(grid, tk.C.Qt.Key.Key_C, tk.C.Qt.KeyboardModifier.ControlModifier)
            assert tk.application().clipboard().text() == '=B10-E10'
            total = next(label for label in window._q.findChildren(tk.W.QLabel)
                         if label.accessibleName() == '선택 합계')
            assert total.text().endswith('17,226,010')
            with patch('work_records_ui.simpledialog.askstring', return_value='다른 업무'):
                button.click()
            assert not grid.model().cells and grid.columnWidth(2) != 48
            assert grid.columnSpan(0, 0) == 1
            selector.setCurrentItem(selector.findItems('기금 관리', tk.C.Qt.MatchFlag.MatchExactly)[0])
            assert grid.columnWidth(2) == 48 and grid.model().index(14, 4).data() == '17,226,010'
            grid.setCurrentIndex(model.index(0, 0))
            grid.edit(model.index(0, 0))
            editor = grid.viewport().findChild(tk.W.QLineEdit)
            editor.setText('연도별 배당 내역')
            workspace.close_tab()
            workspace.open('g5c0')
            grid = workspace.tabs['g5c0']._q.findChild(FreeSheet)
            assert grid.columnWidth(2) == 48
            model = grid.model()
            assert model.index(0, 0).data() == '연도별 배당 내역'
            assert grid.columnSpan(0, 0) == 2
            unmerge = next(b for b in workspace.tabs['g5c0']._q.findChildren(tk.W.QPushButton) if b.text() == '병합 해제')
            grid.setCurrentIndex(model.index(0, 0))
            unmerge.click()
            assert grid.columnSpan(0, 0) == 1 and model.book.grid_merges(model.task) == []
            assert model.index(14, 4).data(tk.C.Qt.ItemDataRole.EditRole) == '=B10-E10'
            assert model.index(19, 26).data() == '17,226,010'
        finally:
            root.destroy()
