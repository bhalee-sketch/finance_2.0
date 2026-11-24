"""Upload and inspect a resource ledger inside financial analysis."""
from pathlib import Path

import qt_ui as tk
from qt_ui import filedialog, ttk
from finance_ui import compact_combo
from resource_cashflow import analyze_cashflow
from responsive_ui import wrapping_row
from statement_catalog import amount_text
from statement_ui import table

SUMMARY = '자금계산서 요약'
VIEWS = {
    '대사업별 요약': ('대사업',),
    '재원별 요약': ('재원',),
    '계정·대사업별 상세': ('구분', '관', '항', '목', '대사업'),
}
TOTAL_BACKGROUNDS = {
    '자금수입총계': ('#D9F1E5', '#244437'),
    '자금지출총계': ('#FFEACF', '#523B29'),
}


def total_background(account, palette):
    colors = TOTAL_BACKGROUNDS.get(account)
    if colors:
        return tk.G.QColor(colors[0] if palette.base().color().lightness() > 128 else colors[1])


class AccountHeader(tk.W.QHeaderView):
    def paintSection(self, painter, rect, section):
        account = self.model().headerData(section, self.orientation())
        background = total_background(account, self.palette())
        if background is None:
            return super().paintSection(painter, rect, section)
        painter.save()
        painter.fillRect(rect, background)
        painter.setFont(self.model().headerData(section, self.orientation(), tk.C.Qt.ItemDataRole.FontRole))
        painter.setPen(self.palette().text().color())
        painter.drawText(rect.adjusted(8, 0, -4, 0), self.defaultAlignment(), account)
        painter.restore()


class CashflowAmountDelegate(tk.W.QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if not (option.displayAlignment & tk.C.Qt.AlignmentFlag.AlignRight) or not option.text.startswith('-'):
            return
        if option.text == '-0':
            option.text = '0'
            return
        option.text = f'({option.text[1:]})'
        red = tk.G.QColor('#B42328' if option.palette.base().color().lightness() > 128 else '#FF999C')
        for role in (tk.G.QPalette.ColorRole.Text, tk.G.QPalette.ColorRole.HighlightedText):
            option.palette.setColor(role, red)


class StatementAmountDelegate(CashflowAmountDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        account = index.model().headerData(index.row(), tk.C.Qt.Orientation.Vertical)
        background = total_background(account, option.palette)
        if background is not None:
            option.backgroundBrush = tk.G.QBrush(background)


class FundMenu(tk.W.QMenu):
    """Let several checkable actions be toggled before the menu is dismissed."""
    def mouseReleaseEvent(self, event):
        action = self.actionAt(event.position().toPoint())
        if action and event.button() == tk.C.Qt.MouseButton.LeftButton:
            action.trigger()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self.activeAction() and event.key() in (tk.C.Qt.Key.Key_Space, tk.C.Qt.Key.Key_Return,
                                                    tk.C.Qt.Key.Key_Enter):
            self.activeAction().trigger()
            return
        super().keyPressEvent(event)


class FundComboBox(tk.DropDownComboBox):
    selectionChanged = tk.C.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setSizeAdjustPolicy(tk.W.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.menu = FundMenu(self)
        self.menu.aboutToHide.connect(self.hidePopup)
        self.menu.triggered.connect(self.update_selection)
        self.set_funds([])

    def set_funds(self, funds):
        self.menu.clear()
        self.all_funds = self.menu.addAction('전체 재원')
        self.all_funds.setCheckable(True)
        self.all_funds.setChecked(True)
        self.choices = {}
        for name in funds:
            action = self.menu.addAction((name or '미지정').replace('&', '&&'))
            action.setCheckable(True)
            self.choices[name] = action
        self.clear()
        self.addItem('전체 재원')
        self.setToolTip('')

    def selected_funds(self):
        return {name for name, action in self.choices.items() if action.isChecked()} or None

    def update_selection(self, action):
        if action is self.all_funds:
            for choice in self.choices.values():
                choice.setChecked(False)
        selected = [name or '미지정' for name, choice in self.choices.items() if choice.isChecked()]
        self.all_funds.setChecked(not selected)
        text = selected[0] if selected else '전체 재원'
        if len(selected) > 1:
            text = f'재원 {len(selected)}개 선택'
        self.setItemText(0, text)
        self.setToolTip(', '.join(selected))
        self.selectionChanged.emit()

    def showPopup(self):
        self.menu.setMinimumWidth(self.width())
        self.menu.popup(self.mapToGlobal(tk.C.QPoint(0, self.height())), self.all_funds)


class FundSelector(ttk.Combobox):
    qt_type = FundComboBox


def labeled_combo(bar, title, widget=ttk.Combobox):
    pair = ttk.Frame(bar)
    pair.pack(side='left')
    ttk.Label(pair, text=title).pack(side='left', padx=(0, 6))
    combo = widget(pair, state='readonly')
    combo._q.setAccessibleName(title)
    combo.pack(side='left')
    return combo


def draw_project_statement(grid, report, fund):
    projects, rows = report.project_statement(fund) if report else ([], [])
    headers = [*(name or '대사업 미지정' for name in projects), '합계(원)']
    grid.clear()
    grid.setColumnCount(len(headers))
    grid.setRowCount(len(rows))
    grid.setHorizontalHeaderLabels(headers)
    for row, (account, values) in enumerate(rows):
        label = tk.W.QTableWidgetItem(account)
        bold = values is None or account in ('자금수입총계', '자금지출총계', '수지차액')
        font = grid.font()
        font.setBold(bold)
        label.setFont(font)
        grid.setVerticalHeaderItem(row, label)
        if values is None:
            continue
        total = sum(value for value in values if value is not None)
        for col, value in enumerate([*values, total]):
            if value is None:
                continue
            item = tk.W.QTableWidgetItem(amount_text(value))
            item.setTextAlignment(tk.C.Qt.AlignmentFlag.AlignRight | tk.C.Qt.AlignmentFlag.AlignVCenter)
            item.setFont(font)
            grid.setItem(row, col, item)
    grid.resizeColumnsToContents()
    grid.scrollToTop()
    grid.horizontalScrollBar().setValue(0)


def install_cashflow_tab(notebook, window, jobs, history, display_table):
    frame = ttk.Frame(notebook, padding=8)
    notebook.add(frame, text='재원별 수지분석')
    bar = wrapping_row(frame)
    bar.pack(fill='x')
    upload = ttk.Button(bar, text='원장 엑셀 업로드', command=lambda: choose())
    upload.pack(side='left')
    view = labeled_combo(bar, '보기')
    compact_combo(view, [SUMMARY, *VIEWS])
    view.current(0)
    fund = labeled_combo(bar, '재원', FundSelector)
    note = tk.StringVar(value='계정별 원장을 올리면 자금계산서 계정 기준으로 수입과 지출을 집계합니다.')
    ttk.Label(frame, textvariable=note, style='Muted.TLabel', wraplength=1000).pack(fill='x', pady=6)
    summary = ttk.Frame(frame)
    grid = tk.W.QTableWidget(summary._q)
    grid.setAccessibleName(SUMMARY)
    grid.setItemDelegate(StatementAmountDelegate(grid))
    grid.setVerticalHeader(AccountHeader(tk.C.Qt.Orientation.Vertical, grid))
    grid.setLayoutDirection(tk.C.Qt.LayoutDirection.LeftToRight)
    grid.setAlternatingRowColors(True)
    grid.setEditTriggers(tk.W.QAbstractItemView.EditTrigger.NoEditTriggers)
    grid.verticalHeader().setDefaultAlignment(tk.C.Qt.AlignmentFlag.AlignLeft | tk.C.Qt.AlignmentFlag.AlignVCenter)
    layout = tk.W.QVBoxLayout(summary._q)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(grid)
    detail = ttk.Frame(frame)
    tree = table(detail, ['대사업', '수입(원)', '지출(원)', '수지차액(원)'], auto_scroll=True)
    tree._q.setItemDelegate(CashflowAmountDelegate(tree._q))
    result = None

    def show(event=None):
        name = view.get()
        if name == SUMMARY:
            detail.pack_forget()
            summary.pack(fill='both', expand=True)
            draw_project_statement(grid, result, fund._q.selected_funds())
            return
        summary.pack_forget()
        detail.pack(fill='both', expand=True)
        dimensions = VIEWS[name]
        headers = [*dimensions, '수입(원)', '지출(원)', '수지차액(원)']
        data = result.report(name, fund._q.selected_funds()) if result else []
        start = len(dimensions)
        totals = [sum(row[col] for row in data) for col in range(start, start + 3)]
        formatted = [[*(value or '미지정' for value in row[:start]), *row[start:]] for row in data]
        if result:
            formatted.append(['합계', *([''] * (start - 1)), *totals])
        display_table(tree, headers, formatted, range(start, start + 3))

    def choose():
        reference = history()
        if not reference:
            tk.messagebox.showinfo('재원별 수지분석', '자금계산서 자료를 불러온 후 원장을 선택하세요.', parent=window)
            return
        source = filedialog.askopenfilename(parent=window, title='재원별 수지분석 원장 선택',
                                            filetypes=[('Excel 파일', '*.xls *.xlsx *.xlsm')])
        if not source:
            return

        def done(report):
            nonlocal result
            result = report
            fund._q.set_funds(sorted({key[0] for key in report.amounts}))
            note.set(f'{Path(source).name} · {report.year}년도 원장 · 계정 기준 {report.basis}년도 자금계산서'
                     f' · 교육외수입 제외 · 포함 {report.included:,}행 · 제외 {report.excluded:,}행')
            show()
            jobs.status.set('재원별 수지분석 완료')

        jobs.run(lambda: analyze_cashflow(source, reference), done)

    fund._q.selectionChanged.connect(show)
    view.bind('<<ComboboxSelected>>', show)
    jobs.controls.extend((upload, fund, view))
    show()
    return frame
