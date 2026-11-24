"""Editable workbook-style task notes."""
import csv
from decimal import Decimal
import io
import sqlite3

import qt_ui as tk
from qt_ui import C, G, W, ttk, messagebox, simpledialog
from ui_theme import dark_titlebar
from statement_catalog import amount_text
from work_record_sums import sheet_values
from work_records import RecordBook, SECTIONS


class SumDelegate(W.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if option.text.lstrip().startswith('='):
            value = self.parent().calculated.get((index.row(), index.column()))
            if value is not None:
                option.text = amount_text(value) if isinstance(value, Decimal) else value


class RecordTable(W.QTableWidget):
    pasteRequested = C.Signal(str)

    def __init__(self, rows, columns):
        super().__init__(rows, columns)
        self.calculated = {}
        self.setItemDelegate(SumDelegate(self))

    def recalculate(self):
        rows = [[self.item(row, col).text() for col in range(self.columnCount())]
                for row in range(self.rowCount())]
        self.calculated = sheet_values(rows)
        self.viewport().update()

    def keyPressEvent(self, event):
        if event.matches(G.QKeySequence.StandardKey.Paste):
            text = W.QApplication.clipboard().text()
            if text:
                self.pasteRequested.emit(text)
            return
        super().keyPressEvent(event)


def open_work_records(parent, desktop, center):
    try:
        book = RecordBook(desktop() / 'settings' / '업무 기록.sqlite3')
        tasks = book.tasks()
    except (OSError, sqlite3.Error) as error:
        messagebox.showerror('업무 기록 열기', str(error), parent=parent)
        return

    window = tk.Toplevel(parent)
    window.title('업무 기록장')
    dark_titlebar(window)
    center(window, 1050, 650)
    frame = ttk.Frame(window)
    frame.pack(fill='both', expand=True)
    layout = W.QVBoxLayout(frame._q)
    layout.setContentsMargins(12, 12, 12, 8)
    task_bar = W.QHBoxLayout()
    layout.addLayout(task_bar)
    task_bar.addWidget(W.QLabel('업무'))
    selector = W.QComboBox()
    selector.setAccessibleName('업무 선택')
    selector.setMinimumContentsLength(15)
    task_bar.addWidget(selector, 1)
    tabs = W.QTabBar()
    tabs.setExpanding(False)
    for title in SECTIONS:
        tabs.addTab(title)
    layout.addWidget(tabs)

    row_bar = W.QHBoxLayout()
    layout.addLayout(row_bar)
    table = RecordTable(0, 4)
    table.horizontalHeader().setToolTip('같은 탭의 셀 주소로 합계를 계산합니다. 예: =SUM(B2:B5)')
    table.setAlternatingRowColors(True)
    table.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
    table.verticalHeader().setDefaultSectionSize(30)
    table.horizontalHeader().setStretchLastSection(True)
    layout.addWidget(table, 1)
    status = tk.StringVar()
    window._work_status = status
    label = ttk.Label(frame, textvariable=status, style='Muted.TLabel')
    label._q.setWordWrap(True)
    footer = W.QHBoxLayout()
    layout.addLayout(footer)
    footer.addWidget(label._q, 1)
    label._q.show()
    selection_sum = W.QLabel()
    selection_sum.setAccessibleName('선택 합계')
    footer.addWidget(selection_sum)

    def button(bar, title, callback):
        widget = W.QPushButton(title)
        bar.addWidget(widget)
        def run():
            try:
                finish_edit()
                callback()
            except (ValueError, sqlite3.Error, OSError, csv.Error) as error:
                messagebox.showerror('업무 기록', str(error), parent=window)
        widget.clicked.connect(run)
        return widget

    def section():
        return tabs.tabText(tabs.currentIndex())

    displayed_task = displayed_section = None

    def finish_edit():
        if table.state() != W.QAbstractItemView.State.EditingState:
            return
        editor = table.indexWidget(table.currentIndex())
        if editor is not None:
            table.commitData(editor)
            table.closeEditor(editor, W.QAbstractItemDelegate.EndEditHint.NoHint)

    def load_rows(selected_id=None):
        nonlocal displayed_task, displayed_section
        finish_edit()
        displayed_task, displayed_section = selector.currentData(), section()
        rows = book.rows(displayed_task, displayed_section)
        with C.QSignalBlocker(table):
            table.clearContents()
            table.setRowCount(len(rows))
            table.setHorizontalHeaderLabels([f'{letter} · {title}' for letter, title in zip('ABCD', SECTIONS[section()])])
            for index, (row_id, *values) in enumerate(rows):
                for column, value in enumerate(values):
                    item = W.QTableWidgetItem(value)
                    item.setData(C.Qt.ItemDataRole.UserRole, row_id)
                    table.setItem(index, column, item)
                if row_id == selected_id:
                    table.setCurrentCell(index, 0)
        active = selector.currentIndex() >= 0
        for widget in (rename, remove, tabs, table, add_row):
            widget.setEnabled(active)
        table.recalculate()
        selection_changed()
        if not active:
            status.set('새 업무를 추가해 기록을 시작하세요.')
        elif not rows:
            status.set('행을 추가하거나 Excel에서 복사한 셀을 표에 붙여넣으세요.')
        else:
            status.set('셀 편집 후 Enter 또는 Tab을 누르면 저장됩니다.')

    def selection_changed():
        row = table.currentRow()
        selected = table.selectedIndexes()
        one_row = bool(selected) and all(index.row() == row for index in selected)
        delete.setEnabled(one_row)
        up.setEnabled(one_row and row > 0)
        down.setEnabled(one_row and row < table.rowCount() - 1)
        numbers = [table.calculated.get((index.row(), index.column())) for index in selected]
        if any(isinstance(value, str) for value in numbers):
            selection_sum.setText('선택 합계 · 수식 오류')
        else:
            amounts = [value for value in numbers if value is not None]
            selection_sum.setText('선택 합계  ' + amount_text(sum(amounts)) if amounts else '')

    def load_tasks(items, selected_id=None):
        with C.QSignalBlocker(selector):
            selector.clear()
            for key, name in items:
                selector.addItem(name, key)
            if items:
                selector.setCurrentIndex(max(0, selector.findData(selected_id)))
        load_rows()

    def edit_name(new):
        name = simpledialog.askstring('새 업무' if new else '업무명 변경', '업무명', parent=window,
                                      initialvalue='' if new else selector.currentText())
        if name is not None:
            key = book.name_task(name, None if new else selector.currentData())
            load_tasks(book.tasks(), key)

    def delete_task():
        if messagebox.askyesno('업무 삭제', f'‘{selector.currentText()}’ 업무와 네 탭의 기록을 삭제할까요?', parent=window):
            book.delete_task(selector.currentData())
            load_tasks(book.tasks())

    def append_row():
        key = book.write_cells(selector.currentData(), section(), [], 0, [['']])
        load_rows(key)
        if table.currentItem():
            table.editItem(table.currentItem())

    def remove_row():
        item = table.currentItem()
        if item and messagebox.askyesno('행 삭제', f'{section()}의 {item.row()+1}번째 행을 삭제할까요?', parent=window):
            book.delete_row(item.data(C.Qt.ItemDataRole.UserRole))
            load_rows()

    def move(direction):
        item = table.currentItem()
        if item:
            key = item.data(C.Qt.ItemDataRole.UserRole)
            book.move_row(selector.currentData(), section(), key, direction)
            load_rows(key)

    def save_cell(item):
        table.recalculate()
        selection_changed()
        try:
            book.write_cells(displayed_task, displayed_section, [item.data(C.Qt.ItemDataRole.UserRole)],
                             item.column(), [[item.text()]])
            status.set('저장됨')
        except (ValueError, sqlite3.Error) as error:
            status.set(f'셀 저장 실패 · {error}')
            messagebox.showerror('셀 저장 실패', str(error), parent=window)

    def paste(text):
        row = max(0, table.currentRow())
        column = max(0, table.currentColumn())
        keys = [table.item(i, 0).data(C.Qt.ItemDataRole.UserRole) for i in range(row, table.rowCount())]
        try:
            values = [cells or [''] for cells in csv.reader(io.StringIO(text, newline=''), delimiter='\t')]
            book.write_cells(selector.currentData(), section(), keys, column, values)
        except (ValueError, sqlite3.Error, csv.Error) as error:
            messagebox.showerror('붙여넣기', str(error), parent=window)
            return
        load_rows()
        table.setCurrentCell(row, column)
        status.set(f'{len(values)}행 저장됨')

    button(task_bar, '새 업무', lambda: edit_name(True))
    rename = button(task_bar, '업무명 변경', lambda: edit_name(False))
    remove = button(task_bar, '업무 삭제', delete_task)
    add_row = button(row_bar, '행 추가', append_row)
    delete = button(row_bar, '행 삭제', remove_row)
    up = button(row_bar, '위로', lambda: move(-1))
    down = button(row_bar, '아래로', lambda: move(1))
    row_bar.addStretch()
    selector.currentIndexChanged.connect(lambda _: load_rows())
    tabs.currentChanged.connect(lambda _: load_rows())
    table.itemChanged.connect(save_cell)
    table.itemSelectionChanged.connect(selection_changed)
    table.currentCellChanged.connect(lambda *_: selection_changed())
    table.pasteRequested.connect(paste)
    window.bind('<Destroy>', lambda _: finish_edit(), add='+')
    for index, width in enumerate((210, 280, 200)):
        table.setColumnWidth(index, width)
    load_tasks(tasks)
    return window
