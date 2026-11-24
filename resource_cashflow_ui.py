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


def set_choices(combo, choices):
    compact_combo(combo, choices)
    for i in range(combo._q.count()):
        combo._q.setItemData(i, tk.C.Qt.AlignmentFlag.AlignCenter, tk.C.Qt.ItemDataRole.TextAlignmentRole)
    combo.current(0)


def labeled_combo(bar, title, choices):
    pair = ttk.Frame(bar)
    pair.pack(side='left')
    ttk.Label(pair, text=title).pack(side='left', padx=(0, 6))
    combo = ttk.Combobox(pair, state='readonly')
    combo._q.setAccessibleName(title)
    combo._q.setItemDelegate(tk.W.QStyledItemDelegate(combo._q))
    combo._q.setLabelDrawingMode(tk.W.QComboBox.LabelDrawingMode.UseDelegate)
    set_choices(combo, choices)
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
    fund = labeled_combo(bar, '재원', ['전체 재원'])
    view = labeled_combo(bar, '보기', [SUMMARY, *VIEWS])
    note = tk.StringVar(value='계정별 원장을 올리면 자금계산서 계정 기준으로 수입과 지출을 집계합니다.')
    ttk.Label(frame, textvariable=note, style='Muted.TLabel', wraplength=1000).pack(fill='x', pady=6)
    summary = ttk.Frame(frame)
    grid = tk.W.QTableWidget(summary._q)
    grid.setAccessibleName(SUMMARY)
    grid.setItemDelegate(CashflowAmountDelegate(grid))
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
    funds = [None]

    def show(event=None):
        name = view.get()
        if name == SUMMARY:
            detail.pack_forget()
            summary.pack(fill='both', expand=True)
            draw_project_statement(grid, result, funds[fund.current()])
            return
        summary.pack_forget()
        detail.pack(fill='both', expand=True)
        dimensions = VIEWS[name]
        headers = [*dimensions, '수입(원)', '지출(원)', '수지차액(원)']
        data = result.report(name, funds[fund.current()]) if result else []
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
            nonlocal result, funds
            result = report
            funds = [None, *sorted({key[0] for key in report.amounts})]
            set_choices(fund, ['전체 재원', *(name or '미지정' for name in funds[1:])])
            note.set(f'{Path(source).name} · {report.year}년도 원장 · 계정 기준 {report.basis}년도 자금계산서'
                     f' · 교육외수입 제외 · 포함 {report.included:,}행 · 제외 {report.excluded:,}행')
            show()
            jobs.status.set('재원별 수지분석 완료')

        jobs.run(lambda: analyze_cashflow(source, reference), done)

    fund.bind('<<ComboboxSelected>>', show)
    view.bind('<<ComboboxSelected>>', show)
    jobs.controls.extend((upload, fund, view))
    show()
    return frame
