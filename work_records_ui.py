"""Work records with a task list and one free-form worksheet per task."""
import sqlite3

import qt_ui as tk
from qt_ui import C, W, ttk, messagebox, simpledialog
from ui_theme import dark_titlebar
from statement_catalog import amount_text
from work_record_grid import FreeSheet
from work_records import RecordBook


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
    selector.setObjectName('WorkRecordTaskList')
    selector.setAccessibleName('업무 목록')
    left.addWidget(selector)
    split.addWidget(sidebar)
    grid = FreeSheet(book)
    split.addWidget(grid)
    split.setChildrenCollapsible(False)
    split.setStretchFactor(1, 1)
    split.setSizes([180, 850])
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
            except (ValueError, sqlite3.Error, OSError) as error:
                messagebox.showerror('업무 기록', str(error), parent=window)
        widget.clicked.connect(run)
        return widget

    def finish_edit():
        grid.flush_widths()
        if grid.state() == W.QAbstractItemView.State.EditingState:
            editor = grid.indexWidget(grid.currentIndex())
            if editor is not None:
                grid.commitData(editor)
                grid.closeEditor(editor, W.QAbstractItemDelegate.EndEditHint.NoHint)

    def selected_task():
        item = selector.currentItem()
        return item.data(C.Qt.ItemDataRole.UserRole) if item else None

    def show_task():
        finish_edit()
        task = selected_task()
        active = task is not None
        rename.setEnabled(active)
        remove.setEnabled(active)
        grid.setVisible(active)
        heading.setText(selector.currentItem().text() if active else '업무 기록장')
        selection_sum.clear()
        grid.open_task(task)
        if active:
            grid.setCurrentIndex(grid.model().index(0, 0))
            status.set('원하는 셀에 입력하거나 Excel 범위를 붙여넣으세요. 합계 =SUM(B2:B9) · 차액 =B10-E10')
        else:
            status.set('새 업무를 추가해 기록을 시작하세요.')

    def selection_changed(*_):
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
        name = simpledialog.askstring('새 업무' if new else '업무명 변경', '업무명', parent=window,
                                      initialvalue='' if new else selector.currentItem().text())
        if name is None:
            return
        key = book.name_task(name, None if new else selected_task())
        load_tasks(book.tasks(), key)

    def delete_task():
        if messagebox.askyesno('업무 삭제', f'‘{selector.currentItem().text()}’ 업무와 모든 기록을 삭제할까요?', parent=window):
            book.delete_task(selected_task())
            load_tasks(book.tasks())

    button(task_bar, '새 업무', lambda: edit_name(True))
    rename = button(task_bar, '업무명 변경', lambda: edit_name(False))
    remove = button(task_bar, '업무 삭제', delete_task)
    selector.currentRowChanged.connect(show_task)
    grid.model().status.connect(status.set)
    grid.selectionModel().selectionChanged.connect(selection_changed)
    grid.model().dataChanged.connect(selection_changed)
    window.protocol('WM_DELETE_WINDOW', window.destroy)
    window.bind('<Destroy>', lambda _: finish_edit(), add='+')
    load_tasks(tasks)
    return window
