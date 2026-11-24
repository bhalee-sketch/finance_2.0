"""Free-form worksheet for a single work record. Only populated cells are stored."""
import csv
from decimal import Decimal
import io
import sqlite3

from openpyxl.utils.cell import get_column_letter
from qt_ui import C, G, W
from statement_catalog import amount_text
from work_record_sums import calculate_cells


class FreeSheetModel(C.QAbstractTableModel):
    status = C.Signal(str)
    MAX_ROWS = 1048576
    MAX_COLUMNS = 16384

    def __init__(self, book, parent):
        super().__init__(parent)
        self.book = book
        self.task = None
        self.cells = {}
        self.values = {}
        self.rows, self.columns = 50, 26

    def rowCount(self, parent=C.QModelIndex()):
        return 0 if parent.isValid() else self.rows

    def columnCount(self, parent=C.QModelIndex()):
        return 0 if parent.isValid() else self.columns

    def headerData(self, section, orientation, role=C.Qt.ItemDataRole.DisplayRole):
        if role == C.Qt.ItemDataRole.DisplayRole:
            return get_column_letter(section + 1) if orientation == C.Qt.Orientation.Horizontal else str(section + 1)
        return super().headerData(section, orientation, role)

    def flags(self, index):
        return super().flags(index) | C.Qt.ItemFlag.ItemIsEditable

    def data(self, index, role=C.Qt.ItemDataRole.DisplayRole):
        key = index.row(), index.column()
        raw = self.cells.get(key, '')
        value = self.values.get(key)
        if role == C.Qt.ItemDataRole.EditRole:
            return raw
        if role == C.Qt.ItemDataRole.ToolTipRole:
            return raw or None
        if role == C.Qt.ItemDataRole.DisplayRole:
            if isinstance(value, Decimal):
                return amount_text(value)
            return raw if value is None else value
        if role == C.Qt.ItemDataRole.TextAlignmentRole and isinstance(value, Decimal):
            return C.Qt.AlignmentFlag.AlignRight | C.Qt.AlignmentFlag.AlignVCenter

    def open_task(self, task):
        cells = self.book.grid_values(task)
        self.beginResetModel()
        self.task, self.cells = task, cells
        self.rows, self.columns = self.extent(cells)
        self.recalculate()
        self.endResetModel()

    def extent(self, cells):
        rows = max((r for r, c in cells), default=-1) + 2
        cols = max((c for r, c in cells), default=-1) + 2
        return min(self.MAX_ROWS, max(50, rows)), min(self.MAX_COLUMNS, max(26, cols))

    def recalculate(self):
        self.values = calculate_cells(self.cells, self.MAX_ROWS, self.MAX_COLUMNS, arithmetic=True)

    def setData(self, index, value, role=C.Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != C.Qt.ItemDataRole.EditRole:
            return False
        return self.write({(index.row(), index.column()): value})

    def write(self, changes):
        if not changes:
            return True
        if any(r < 0 or r >= self.MAX_ROWS or c < 0 or c >= self.MAX_COLUMNS for r, c in changes):
            self.status.emit('붙여넣을 범위가 시트 크기를 초과합니다.')
            return False
        try:
            self.book.save_grid(self.task, changes)
        except (sqlite3.Error, OSError) as error:
            self.status.emit(f'셀 저장 실패 · {error}')
            return False
        for key, value in changes.items():
            if value:
                self.cells[key] = value
            else:
                self.cells.pop(key, None)
        rows, columns = self.extent(changes)
        if rows > self.rows:
            self.beginInsertRows(C.QModelIndex(), self.rows, rows - 1)
            self.rows = rows
            self.endInsertRows()
        if columns > self.columns:
            self.beginInsertColumns(C.QModelIndex(), self.columns, columns - 1)
            self.columns = columns
            self.endInsertColumns()
        self.recalculate()
        self.dataChanged.emit(self.index(0, 0), self.index(self.rows - 1, self.columns - 1))
        self.status.emit('저장됨')
        return True


class FreeSheet(W.QTableView):
    def __init__(self, book):
        super().__init__()
        self.setAccessibleName('자유 시트')
        self.setModel(FreeSheetModel(book, self))
        self.setSelectionMode(W.QAbstractItemView.SelectionMode.ContiguousSelection)
        self.horizontalHeader().setMinimumSectionSize(24)
        self.horizontalHeader().setDefaultSectionSize(max(96, self.fontMetrics().horizontalAdvance('999,999,999') + 20))
        self.verticalHeader().setDefaultSectionSize(26)
        self.setWordWrap(False)
        self.widths = {}
        self.pending_widths = {}
        self.width_timer = C.QTimer(self)
        self.width_timer.setSingleShot(True)
        self.width_timer.timeout.connect(self.flush_widths)
        self.horizontalHeader().sectionResized.connect(self.width_changed)

    def width_changed(self, column, old_size, size):
        if self.model().task is not None and size > 0:
            self.widths[column] = self.pending_widths[column] = size
            self.width_timer.start(250)

    def flush_widths(self):
        self.width_timer.stop()
        if self.pending_widths:
            try:
                self.model().book.save_grid_widths(self.model().task, self.pending_widths)
            except sqlite3.Error as error:
                self.model().status.emit(f'열 너비 저장 실패 · {error}')
                return
            self.pending_widths.clear()

    def open_task(self, task):
        header = self.horizontalHeader()
        with C.QSignalBlocker(header):
            for column in self.widths:
                header.resizeSection(column, header.defaultSectionSize())
            self.model().open_task(task)
            self.widths = self.model().book.grid_widths(task)
            self.pending_widths.clear()
            for column, size in self.widths.items():
                header.resizeSection(column, size)

    def keyPressEvent(self, event):
        sheet = self.model()
        current = self.currentIndex()
        if event.matches(G.QKeySequence.StandardKey.Paste):
            if not current.isValid():
                current = sheet.index(0, 0)
            text = W.QApplication.clipboard().text()
            if text:
                try:
                    rows = csv.reader(io.StringIO(text, newline=''), delimiter='\t')
                    changes = {(current.row()+r, current.column()+c): raw
                               for r, row in enumerate(rows) for c, raw in enumerate(row or [''])}
                    sheet.write(changes)
                except csv.Error as error:
                    sheet.status.emit(f'붙여넣기 실패 · {error}')
            return
        selection = self.selectionModel().selection()
        if selection and event.matches(G.QKeySequence.StandardKey.Copy):
            top = min(area.top() for area in selection)
            bottom = max(area.bottom() for area in selection)
            left = min(area.left() for area in selection)
            right = max(area.right() for area in selection)
            output = io.StringIO(newline='')
            writer = csv.writer(output, delimiter='\t', lineterminator='\n')
            for row in range(top, bottom+1):
                writer.writerow([sheet.cells.get((row, col), '') for col in range(left, right+1)])
            W.QApplication.clipboard().setText(output.getvalue().removesuffix('\n'))
            return
        if selection and event.key() == C.Qt.Key.Key_Delete:
            sheet.write({key: '' for key in sheet.cells if selection.contains(sheet.index(*key))})
            return
        super().keyPressEvent(event)
