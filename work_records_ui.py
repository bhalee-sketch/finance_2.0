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
from work_record_grid import FreeSheet
from work_records import CASHBOOK, FREE_SHEET, RecordBook, SECTIONS


class SumDelegate(W.QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if index.column() == 1 and index.model().columnCount() == len(SECTIONS[CASHBOOK]) and isinstance(editor, W.QLineEdit):
            table = self.parent()
            sources = {table.item(row, 1).text().strip() for row in range(table.rowCount())}
            completer = W.QCompleter(sorted(sources - {''}), editor)
            editor.setCompleter(completer)
        return editor

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        value = self.parent().calculated.get((index.row(), index.column()))
        if index.column() in (5, 6) and isinstance(value, Decimal):
            option.text = amount_text(value)
            option.displayAlignment = C.Qt.AlignmentFlag.AlignRight | C.Qt.AlignmentFlag.AlignVCenter
        elif option.text.lstrip().startswith('='):
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


def new_task_details(window):
    from appearance import controller
    dialog = W.QDialog(window._q)
    dialog.setWindowTitle('새 업무')
    layout = W.QFormLayout(dialog)
    name = W.QLineEdit()
    layout.addRow('업무명', name)
    formats = W.QComboBox()
    formats.addItem('엑셀형', 'sheet')
    formats.addItem('메모장형', 'memo')
    layout.addRow('기록 형식', formats)
    buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Ok | W.QDialogButtonBox.StandardButton.Cancel)
    create = buttons.button(W.QDialogButtonBox.StandardButton.Ok)
    create.setText('만들기')
    create.setEnabled(False)
    name.textChanged.connect(lambda text: create.setEnabled(bool(text.strip())))
    buttons.button(W.QDialogButtonBox.StandardButton.Cancel).setText('취소')
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addRow(buttons)
    appearance = controller(window)
    dark_titlebar(dialog, theme=appearance.theme if appearance else 'light')
    try:
        if dialog.exec() == W.QDialog.DialogCode.Accepted:
            return name.text(), formats.currentData()
    finally:
        dialog.deleteLater()


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
    heading = W.QLabel('업무 기록장')
    heading.setTextFormat(C.Qt.TextFormat.PlainText)
    heading.setObjectName('WorkspaceSection')
    task_bar.addWidget(heading, 1)
    split = W.QSplitter(C.Qt.Orientation.Horizontal)
    layout.addWidget(split, 1)
    sidebar = W.QWidget()
    left = W.QVBoxLayout(sidebar)
    left.setContentsMargins(0, 0, 6, 0)
    left.addWidget(W.QLabel('업무 목록'))
    selector = W.QListWidget()
    selector.setAccessibleName('업무 목록')
    left.addWidget(selector)
    split.addWidget(sidebar)
    pages = W.QStackedWidget()
    split.addWidget(pages)
    split.setChildrenCollapsible(False)
    split.setStretchFactor(1, 1)
    split.setSizes([180, 850])
    sheet = W.QWidget()
    sheet_layout = W.QVBoxLayout(sheet)
    sheet_layout.setContentsMargins(0, 0, 0, 0)
    pages.addWidget(sheet)
    memo = W.QPlainTextEdit()
    memo.setAccessibleName('업무 메모')
    memo.setPlaceholderText('이 업무의 내용을 자유롭게 기록하세요.')
    pages.addWidget(memo)
    empty = W.QWidget()
    pages.addWidget(empty)
    memo_timer = C.QTimer(memo)
    memo_timer.setSingleShot(True)
    memo_timer.setInterval(400)
    memo_original = None
    tabs = W.QTabBar()
    tabs.setExpanding(False)
    titles = [FREE_SHEET, *SECTIONS]
    for title in titles:
        tabs.addTab(title)
    sheet_layout.addWidget(tabs)

    row_tools = W.QWidget()
    row_bar = W.QHBoxLayout(row_tools)
    row_bar.setContentsMargins(0, 0, 0, 0)
    sheet_layout.addWidget(row_tools)
    grid = FreeSheet(book)
    sheet_layout.addWidget(grid, 1)
    table = RecordTable(0, 4)
    table.horizontalHeader().setToolTip('같은 탭의 셀 주소로 합계를 계산합니다. 예: =SUM(B2:B5)')
    table.setAlternatingRowColors(True)
    table.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection)
    table.verticalHeader().setDefaultSectionSize(30)
    table.horizontalHeader().setStretchLastSection(True)
    sheet_layout.addWidget(table, 1)
    balance = W.QLabel()
    balance.setTextFormat(C.Qt.TextFormat.PlainText)
    balance.setAccessibleName('수입·지출 합계')
    balance.setWordWrap(True)
    sheet_layout.addWidget(balance)
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
                if save_memo():
                    callback()
            except (ValueError, sqlite3.Error, OSError, csv.Error) as error:
                messagebox.showerror('업무 기록', str(error), parent=window)
        widget.clicked.connect(run)
        return widget

    def section():
        return tabs.tabText(tabs.currentIndex())

    displayed_task = displayed_section = None

    def finish_edit():
        grid.flush_widths()
        for view in (grid, table):
            if view.state() == W.QAbstractItemView.State.EditingState:
                editor = view.indexWidget(view.currentIndex())
                if editor is not None:
                    view.commitData(editor)
                    view.closeEditor(editor, W.QAbstractItemDelegate.EndEditHint.NoHint)

    def selected_task():
        item = selector.currentItem()
        return item.data(C.Qt.ItemDataRole.UserRole) if item else None

    def save_memo():
        nonlocal memo_original
        memo_timer.stop()
        if memo_original is None:
            return True
        text = memo.toPlainText()
        if text == memo_original:
            return True
        try:
            book.save_memo(displayed_task, text, memo_original)
        except (ValueError, sqlite3.Error) as error:
            status.set(f'메모 저장 실패 · {error}')
            return False
        memo_original = text
        memo.document().setModified(False)
        status.set('메모 저장됨')
        return True

    def show_task():
        nonlocal displayed_task, memo_original
        finish_edit()
        if not save_memo():
            with C.QSignalBlocker(selector):
                for i in range(selector.count()):
                    if selector.item(i).data(C.Qt.ItemDataRole.UserRole) == displayed_task:
                        selector.setCurrentRow(i)
                        break
            return
        task = selected_task()
        record_format, text, first = book.task_content(task) if task is not None else ('sheet', '', CASHBOOK)
        displayed_task = task
        memo_original = text if record_format == 'memo' else None
        active = task is not None
        rename.setEnabled(active)
        remove.setEnabled(active)
        heading.setText(selector.currentItem().text() if active else '업무 기록장')
        selection_sum.clear()
        if not active:
            pages.setCurrentWidget(empty)
            status.set('새 업무를 추가해 기록을 시작하세요.')
            return
        if record_format == 'memo':
            with C.QSignalBlocker(memo):
                memo.setPlainText(text)
                memo.document().setModified(False)
            pages.setCurrentWidget(memo)
            status.set('메모는 자동으로 저장됩니다.')
            return
        pages.setCurrentWidget(sheet)
        with C.QSignalBlocker(tabs):
            tabs.setCurrentIndex(titles.index(first))
        load_rows()

    def load_rows(selected_id=None):
        nonlocal displayed_task, displayed_section
        finish_edit()
        displayed_task, displayed_section = selected_task(), section()
        free = displayed_section == FREE_SHEET
        grid.setVisible(free)
        table.setVisible(not free)
        row_tools.setVisible(not free)
        if free:
            balances.clear()
            balance.hide()
            selection_sum.clear()
            grid.open_task(displayed_task)
            grid.setCurrentIndex(grid.model().index(0, 0))
            status.set('원하는 셀에 입력하거나 Excel 범위를 붙여넣으세요. 합계 =SUM(B2:B9) · 차액 =B10-E10')
            return
        rows = book.rows(displayed_task, displayed_section)
        with C.QSignalBlocker(table):
            table.clearContents()
            headers = SECTIONS[section()]
            table.setColumnCount(len(headers))
            table.setRowCount(len(rows))
            table.setHorizontalHeaderLabels([f'{letter} · {title}' for letter, title in zip('ABCDEFG', headers)])
            if section() == CASHBOOK:
                table.horizontalHeaderItem(1).setToolTip('같은 입금에서 사용한 지출에는 같은 재원·입금 건을 입력하세요.')
            for index, (row_id, *values) in enumerate(rows):
                for column, value in enumerate(values):
                    item = W.QTableWidgetItem(value)
                    item.setData(C.Qt.ItemDataRole.UserRole, row_id)
                    table.setItem(index, column, item)
                if row_id == selected_id:
                    table.setCurrentCell(index, 0)
        table.recalculate()
        refresh_balances()
        selection_changed()
        if not rows:
            status.set('행을 추가하거나 Excel에서 복사한 셀을 표에 붙여넣으세요.')
        else:
            status.set('셀 편집 후 Enter 또는 Tab을 누르면 저장됩니다.')

    balances = {}
    def refresh_balances():
        balances.clear()
        balance.setVisible(displayed_section == CASHBOOK)
        if displayed_section != CASHBOOK:
            return
        balances[None] = [Decimal(0), Decimal(0)]
        for row in range(table.rowCount()):
            source = table.item(row, 1).text().strip()
            groups = [balances[None]]
            if source:
                groups.append(balances.setdefault(source, [Decimal(0), Decimal(0)]))
            for side, col in enumerate((5, 6)):
                if table.item(row, col).text().strip():
                    value = table.calculated.get((row, col))
                    for group in groups:
                        if not isinstance(value, Decimal):
                            group[side] = None
                        elif group[side] is not None:
                            group[side] += value

    def balance_text(name, totals):
        income, expense = totals
        remaining = income - expense if None not in totals else None
        def money(value):
            return '금액 확인 필요' if value is None else amount_text(value) + '원'
        return f'{name}   수입 {money(income)}   지출 {money(expense)}   잔액 {money(remaining)}'

    def selection_changed():
        row = table.currentRow()
        if balances:
            lines = [balance_text('전체', balances[None])]
            source = table.item(row, 1).text().strip() if row >= 0 else ''
            if source in balances:
                lines.append(balance_text(source, balances[source]))
            balance.setText('\n'.join(lines))
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

    def free_selection_changed(*_):
        if displayed_section != FREE_SHEET:
            return
        model = grid.model()
        selection = grid.selectionModel().selection()
        values = [value for key, value in model.values.items() if selection.contains(model.index(*key))]
        if any(isinstance(value, str) for value in values):
            selection_sum.setText('선택 합계 · 수식 오류')
        else:
            selection_sum.setText('선택 합계  ' + amount_text(sum(values)) if values else '')

    def load_tasks(items, selected_id=None):
        with C.QSignalBlocker(selector):
            selector.clear()
            selected = 0
            for i, (key, name) in enumerate(items):
                item = W.QListWidgetItem(name)
                item.setData(C.Qt.ItemDataRole.UserRole, key)
                selector.addItem(item)
                if key == selected_id:
                    selected = i
            if items:
                selector.setCurrentRow(selected)
        show_task()

    def edit_name(new):
        if new:
            details = new_task_details(window)
            if details is None:
                return
            name, record_format = details
            key = book.name_task(name, record_format=record_format)
        else:
            name = simpledialog.askstring('업무명 변경', '업무명', parent=window,
                                          initialvalue=selector.currentItem().text())
            if name is None:
                return
            key = book.name_task(name, selected_task())
        load_tasks(book.tasks(), key)

    def delete_task():
        if messagebox.askyesno('업무 삭제', f'‘{selector.currentItem().text()}’ 업무와 모든 기록을 삭제할까요?', parent=window):
            book.delete_task(selected_task())
            load_tasks(book.tasks())

    def append_row():
        key = book.write_cells(selected_task(), section(), [], 0, [['']])
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
            book.move_row(selected_task(), section(), key, direction)
            load_rows(key)

    def save_cell(item):
        table.recalculate()
        refresh_balances()
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
            book.write_cells(selected_task(), section(), keys, column, values)
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
    selector.currentRowChanged.connect(lambda _: show_task())
    memo.textChanged.connect(memo_timer.start)
    memo_timer.timeout.connect(save_memo)
    tabs.currentChanged.connect(lambda _: load_rows())
    grid.model().status.connect(status.set)
    grid.selectionModel().selectionChanged.connect(free_selection_changed)
    grid.model().dataChanged.connect(free_selection_changed)
    table.itemChanged.connect(save_cell)
    table.itemSelectionChanged.connect(selection_changed)
    table.currentCellChanged.connect(lambda *_: selection_changed())
    table.pasteRequested.connect(paste)
    def flush_edits(_=None):
        finish_edit()
        return save_memo()

    window.protocol('WM_DELETE_WINDOW', lambda: window.destroy() if flush_edits() else None)
    window.bind('<Destroy>', flush_edits, add='+')
    for index, width in enumerate((120, 160, 150)):
        table.setColumnWidth(index, width)
    load_tasks(tasks)
    return window
