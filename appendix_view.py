"""Bundled appendix sheets in workbook order, with cached formula results."""
from pathlib import Path

import qt_ui as tk
from qt_ui import ttk
from openpyxl.utils import get_column_letter

from statement_database import StatementSource, read_workbook, connect
from statement_loader import _cell_display_text
from statement_ui import Jobs

DATA = Path(__file__).resolve().parent / 'data' / 'appendices'
SOURCES = {'재무상태표': DATA / 'balance.sqlite3', '운영계산서': DATA / 'operation.sqlite3'}


def list_sheets(kind):
    with connect(SOURCES[kind]) as connection:
        return [name for name, in connection.execute(
            'SELECT s.name FROM sheets s JOIN workbooks w ON w.id=s.workbook_id '
            'WHERE w.fiscal_year=2025 ORDER BY s.position')]


def open_appendix_view(parent, center):
    window = tk.Toplevel(parent, show_on_create=False)
    window.title('부속명세서 조회')
    center(window, 1200, 750)
    body = ttk.Frame(window, padding=12); body.pack(fill='both', expand=True)
    toolbar = ttk.Frame(body); toolbar.pack(fill='x', pady=(0, 10))
    ttk.Label(toolbar, text='2025회계연도').pack(side='left', padx=(0, 16))
    kind = tk.StringVar(value='재무상태표'); sheet_name = tk.StringVar()
    ttk.Label(toolbar, textvariable=kind).pack(side='left')
    host = ttk.Frame(body); host.pack(fill='both', expand=True)
    layout = tk.W.QVBoxLayout(host._q); layout.setContentsMargins(0, 0, 0, 0)
    table = tk.W.QTableWidget(); layout.addWidget(table)
    table.setSortingEnabled(False); table.horizontalHeader().setSectionsClickable(False)
    table.horizontalHeader().setSortIndicatorShown(False)
    table.horizontalHeader().setStretchLastSection(False)
    table.setEditTriggers(tk.W.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setWordWrap(True)
    status = tk.StringVar(); ttk.Label(body, textvariable=status).pack(anchor='w', pady=(8, 0))
    tab_host = ttk.Frame(body); tab_host.pack(fill='x')
    tab_layout = tk.W.QVBoxLayout(tab_host._q); tab_layout.setContentsMargins(0, 0, 0, 0)
    tabs = tk.W.QTabBar(); tabs.setAccessibleName('부속명세서 시트')
    tabs.setShape(tk.W.QTabBar.Shape.RoundedSouth)
    tabs.setExpanding(False); tabs.setUsesScrollButtons(True); tabs.setMinimumWidth(0)
    tabs.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored, tk.W.QSizePolicy.Policy.Fixed)
    tab_layout.addWidget(tabs)
    entries = [(category, name) for category in SOURCES for name in list_sheets(category)]
    for category, name in entries:
        index = tabs.addTab(name); tabs.setTabToolTip(index, category + ' · ' + name)
    jobs = Jobs(window, status, show_loading=False); jobs.controls = [tab_host]
    window._appendix_table = table
    window._appendix_tabs = tabs
    window._appendix_sheet_entries = entries

    def fonts(event=None):
        from appearance import controller
        appearance = controller(window)
        if not appearance:return
        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                item = table.item(row, column)
                if item is None:continue
                font = tk.G.QFont(table.font())
                font.setFamily((appearance.numeric_family or appearance.family)
                               if item.data(tk.C.Qt.ItemDataRole.UserRole) else appearance.family)
                item.setFont(font)
        table.resizeRowsToContents()

    def show_sheet():
        if jobs.busy or not sheet_name.get():return
        selected_kind, selected_sheet = kind.get(), sheet_name.get()
        def load():
            workbook = read_workbook(StatementSource(SOURCES[selected_kind], '2025'))
            return workbook
        def display(workbook):
            try:
                sheet = workbook[selected_sheet]
                table.setUpdatesEnabled(False)
                table.clearSpans(); table.clear()
                table.setRowCount(sheet.max_row); table.setColumnCount(sheet.max_column)
                table.setHorizontalHeaderLabels([get_column_letter(c) for c in range(1, sheet.max_column + 1)])
                for col in range(sheet.max_column):table.setColumnWidth(col, 150)
                for row in sheet:
                    for cell in row:
                        if cell.value is None:continue
                        item = tk.W.QTableWidgetItem(_cell_display_text(cell))
                        numeric = isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
                        item.setData(tk.C.Qt.ItemDataRole.UserRole, numeric)
                        item.setTextAlignment((tk.C.Qt.AlignmentFlag.AlignRight if numeric else tk.C.Qt.AlignmentFlag.AlignLeft)
                                              | tk.C.Qt.AlignmentFlag.AlignVCenter)
                        table.setItem(cell.row - 1, cell.column - 1, item)
                for merged in sheet.merged_cells.ranges:
                    table.setSpan(merged.min_row - 1, merged.min_col - 1,
                                  merged.max_row - merged.min_row + 1, merged.max_col - merged.min_col + 1)
                fonts()
                status.set(f'2025년 · {selected_kind} · {selected_sheet} · {sheet.max_row:,}행')
            finally:
                table.setUpdatesEnabled(True); workbook.close()
        jobs.run(load, display)

    def change_sheet(index):
        if jobs.busy or index < 0:return
        category, name = entries[index]
        kind.set(category); sheet_name.set(name)
        show_sheet()

    tabs.currentChanged.connect(change_sheet)
    window.bind('<<ThemeChanged>>', fonts)
    window.after(100, lambda: change_sheet(tabs.currentIndex()))
    window.deiconify()
    return window
