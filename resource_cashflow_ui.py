"""Upload and inspect a resource ledger inside financial analysis."""
from datetime import date
from zipfile import BadZipFile

import qt_ui as tk
from qt_ui import filedialog, ttk
from finance_ui import compact_combo
from resource_cashflow import read_cashflow, saved_cashflow_years, store_cashflow
from responsive_ui import wrapping_row
from statement_catalog import amount_text
from statement_ui import table

SUMMARY = '자금계산서 요약'
VIEWS = {
    '대사업별 요약': '대사업',
    '재원별 요약': '재원',
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


class FundSelectionDialog(tk.W.QDialog):
    def __init__(self, window, funds, selected):
        super().__init__(window._q)
        from appearance import controller
        from ui_theme import dark_titlebar

        self.setWindowTitle('재원 선택')
        layout = tk.W.QVBoxLayout(self)
        self.all_funds = tk.W.QCheckBox('전체 재원')
        layout.addWidget(self.all_funds)

        scroll = tk.W.QScrollArea()
        scroll.setWidgetResizable(True)
        contents = tk.W.QWidget()
        rows = tk.W.QVBoxLayout(contents)
        self.choices = {}
        for name in funds:
            check = tk.W.QCheckBox((name or '미지정').replace('&', '&&'))
            check.setChecked(selected is not None and name in selected)
            check.clicked.connect(self.sync_all)
            rows.addWidget(check)
            self.choices[name] = check
        rows.addStretch()
        scroll.setWidget(contents)
        layout.addWidget(scroll)
        self.sync_all()
        self.all_funds.clicked.connect(self.select_all)

        buttons = tk.W.QDialogButtonBox()
        apply = buttons.addButton('선택 적용', tk.W.QDialogButtonBox.ButtonRole.AcceptRole)
        apply.setProperty('role', 'Primary.TButton')
        apply.setDefault(True)
        buttons.addButton('취소', tk.W.QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.setCenterButtons(True)
        layout.addWidget(buttons)
        self.resize(420, min(480, max(220, contents.sizeHint().height() + 110)))
        appearance = controller(window)
        dark_titlebar(self, theme=appearance.theme if appearance else 'light')

    def selected_funds(self):
        return {name for name, check in self.choices.items() if check.isChecked()} or None

    def sync_all(self):
        self.all_funds.setChecked(self.selected_funds() is None)

    def select_all(self):
        for check in self.choices.values():
            check.setChecked(False)
        self.all_funds.setChecked(True)


def draw_fund_statement(grid, report, fund):
    funds, rows = report.fund_statement(fund) if report else ([], [])
    headers = [*(name or '재원 미지정' for name in funds), '합계(원)']
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


def install_cashflow_tab(notebook, window, jobs, history, display_table, folder):
    frame = ttk.Frame(notebook, padding=8)
    notebook.add(frame, text='재원별 수지분석')
    bar = wrapping_row(frame, uniform_height=True)
    bar._q.setObjectName('CashflowToolbar')
    bar.pack(fill='x')
    def labeled_box(title):
        pair = ttk.Frame(bar)
        pair.pack(side='left')
        ttk.Label(pair, text=title).pack(side='left', padx=(0, 6))
        box = ttk.Combobox(pair, state='readonly')
        box._q.setAccessibleName(title)
        box.pack(side='left', fill='y')
        return box

    year_box = labeled_box('회계연도')
    upload = ttk.Button(bar, text='원장 엑셀 업로드', command=lambda: choose())
    upload.pack(side='left')
    view = labeled_box('보기')
    compact_combo(view, [SUMMARY, *VIEWS])
    view.current(0)
    fund = ttk.Button(bar, text='재원 선택 · 전체 재원', state='disabled', command=lambda: choose_funds())
    fund.pack(side='left')
    for control in (year_box, upload, view, fund):
        policy = control._q.sizePolicy()
        policy.setVerticalPolicy(tk.W.QSizePolicy.Policy.Minimum)
        control._q.setSizePolicy(policy)
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
    available_funds = []
    selected_funds = None

    def choose_funds():
        dialog = FundSelectionDialog(window, available_funds, selected_funds)
        try:
            if dialog.exec() == tk.W.QDialog.DialogCode.Accepted:
                apply_funds(dialog.selected_funds())
        finally:
            dialog.deleteLater()

    def apply_funds(selection):
        nonlocal selected_funds
        selected_funds = selection
        names = [name or '미지정' for name in available_funds if selection and name in selection]
        caption = names[0] if names else '전체 재원'
        if len(names) > 1:
            caption = f'{len(names)}개 선택'
        fund.configure(text=f'재원 선택 · {caption}')
        fund._q.setToolTip(', '.join(names))
        show()

    def show(event=None):
        name = view.get()
        if name == SUMMARY:
            detail.pack_forget()
            summary.pack(fill='both', expand=True)
            draw_fund_statement(grid, result, selected_funds)
            return
        summary.pack_forget()
        detail.pack(fill='both', expand=True)
        headers = [VIEWS[name], '수입(원)', '지출(원)', '수지차액(원)']
        data = result.report(name, selected_funds) if result else []
        formatted = [[label or '미지정', *amounts] for label, *amounts in data]
        if result:
            totals = [sum(row[col] for row in data) for col in range(1, 4)]
            formatted.append(['합계', *totals])
        display_table(tree, headers, formatted, range(1, 4))

    def display_year(year, saved=None):
        nonlocal result, available_funds
        result = saved[1] if saved else None
        available_funds = sorted({key[0] for key in result.amounts}) if result else []
        fund.configure(state='normal' if available_funds else 'disabled')
        if saved:
            filename, report = saved
            note.set(f'{year}회계연도 · {filename} · 원장 {report.year}년도 · 계정 기준 {report.basis}년도 자금계산서'
                     f' · 교육외수입 제외 · 포함 {report.included:,}행 · 제외 {report.excluded:,}행')
        else:
            note.set(f'{year}회계연도에 저장된 원장이 없습니다. 원장 엑셀을 업로드하세요.')
        apply_funds(None)

    def open_year(event=None):
        year = year_box.get()
        try:
            saved = read_cashflow(folder, year)
        except FileNotFoundError:
            saved = None
        except (OSError, BadZipFile, KeyError, ValueError) as error:
            display_year(year)
            note.set(f'{year}회계연도 저장 자료를 열 수 없습니다.')
            tk.messagebox.showerror('저장 원장 조회', str(error), parent=window)
            return
        display_year(year, saved)

    def refresh_years():
        current = str(date.today().year)
        saved = saved_cashflow_years(folder)
        previous = year_box.get()
        years = sorted({current, str(int(current) - 1), *history(), *saved}, reverse=True)
        chosen = previous if previous in years else next(iter(saved), current)
        compact_combo(year_box, years)
        year_box.current(years.index(chosen))
        if not previous or chosen != previous:
            open_year()

    def choose():
        reference = history()
        if not reference:
            tk.messagebox.showinfo('재원별 수지분석', '자금계산서 자료를 불러온 후 원장을 선택하세요.', parent=window)
            return
        year = year_box.get()
        source = filedialog.askopenfilename(parent=window, title=f'{year}회계연도에 저장할 원장 선택',
                                            filetypes=[('Excel 파일', '*.xls *.xlsx *.xlsm')])
        if not source:
            return
        if (folder / f'{year}.zip').exists() and not tk.messagebox.askyesno(
                '원장 교체', f'{year}회계연도에 저장된 원장을 새 파일로 교체할까요?', parent=window):
            return

        def done(saved):
            display_year(year, saved)
            jobs.status.set(f'{year}회계연도 재원별 수지분석 저장 완료')

        jobs.run(lambda: store_cashflow(folder, year, source, reference), done)

    year_box.bind('<<ComboboxSelected>>', open_year)
    view.bind('<<ComboboxSelected>>', show)
    jobs.controls.extend((upload, fund, view, year_box))
    show()
    return frame, refresh_years
