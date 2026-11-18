"""차입금 관리의 회계연도별 납부·예정 추이와 분기별 상환 내역."""
from decimal import Decimal
from pathlib import Path

import qt_ui as tk
from qt_ui import messagebox, ttk

from analysis_charts import lines
from analysis_topics import loan_dashboard
from finance_ui import apply_widths, content_widths, fill, saved, target_file
from loan_manager import HEADERS, uploaded_loan_sources
from statement_ui import table
from responsive_ui import wrapping_row


def install_repayment_tab(notebook, window, storage, report_year, task, status, open_file):
    page = ttk.Frame(notebook, padding=8)
    notebook.add(page, text='차입금·이자 상환')
    controls = wrapping_row(page)
    controls.pack(fill='x')
    ttk.Button(controls, text='상환 자료 새로고침', command=lambda: load()).pack(side='left')
    mode = tk.StringVar(value='납부 기준')
    for label in ('납부 기준', '예정 기준', '잔여 예정액'):
        ttk.Radiobutton(controls, text=label, variable=mode, value=label, command=lambda: render(),
                        style='Statement.TRadiobutton').pack(side='left')

    def year_control(label, initial=''):
        group = ttk.Frame(controls)
        group.pack(side='left')
        ttk.Label(group, text=label).pack(side='left', anchor='w', padx=(0, 4))
        variable = tk.StringVar(value=initial)
        combo = ttk.Combobox(group, textvariable=variable, state='readonly', width=7)
        combo.pack(side='left', anchor='w')
        combo.bind('<<ComboboxSelected>>', lambda event: render())
        return variable, combo

    year, year_box = year_control('분기 조회 연도')
    start, start_box = year_control('그래프 시작연도', '전체')
    export_button = ttk.Button(controls, text='상환 분석 Excel 저장', state='disabled', command=lambda: export())
    export_button.pack(side='left')

    note = tk.StringVar()
    description = ttk.Label(page, textvariable=note, style='Muted.TLabel', wraplength=800)
    description._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored, tk.W.QSizePolicy.Policy.Preferred)
    description.pack(fill='x', pady=5)
    details = ttk.LabelFrame(page, text='분기별 상세 내역 · 원')
    details.pack(side='bottom', fill='x')
    headers = ['분기', *HEADERS]
    tree = table(details, headers, auto_scroll=True)
    tree._q.setFixedHeight(200)
    canvas = tk.Canvas(page, bg='#192131', highlightthickness=0)
    canvas._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored, tk.W.QSizePolicy.Policy.Ignored)
    canvas._q.setMinimumHeight(180)
    canvas.pack(fill='both', expand=True)
    canvas.bind('<Configure>', lambda event: draw())

    annual = []
    quarters = {}
    sources = []
    plot_headers = []
    plot_rows = []
    loaded = False

    def draw():
        if plot_rows:
            lines(canvas, plot_headers, plot_rows, '금액', hide_zero=True, name_labels=True)
        else:
            canvas.delete('all')

    def render():
        nonlocal plot_headers, plot_rows
        if not loaded:
            return
        if mode.get() == '잔여 예정액':
            remaining = [Decimal(0), Decimal(0)]
            rows = []
            for fiscal_year, principal, interest, _, _ in reversed(annual):
                rows.append([fiscal_year, *remaining])
                remaining[0] += principal
                remaining[1] += interest
            rows.reverse()
            plot_headers = ['회계연도', '잔여 예정 원금', '잔여 예정 이자']
            basis = '각 연도 말 이후 예정 일정의 합계'
        else:
            principal, interest = (3, 4) if mode.get() == '납부 기준' else (1, 2)
            rows = [[row[0], row[principal], row[interest]] for row in annual]
            plot_headers = ['회계연도', '원금', '이자']
            basis = '납부는 실제 납부일, 예정은 예정일 기준'
        plot_rows = [row for row in rows if start.get() == '전체' or row[0] >= start.get()]
        note.set(basis+' · 3월~다음해 2월 회계연도 · 분기는 3~5 / 6~8 / 9~11 / 12~2월')
        values = quarters.get(year.get(), [])
        fill(tree, headers, values, range(1, len(headers)-1))
        tree.column(str(len(headers)-1), anchor='center')
        apply_widths(tree, content_widths(tree, headers, values))
        tree.tag_configure('total', background='#244C70', foreground='#FFFFFF')
        tree.tag_configure('attention', background='#54472B', foreground='#FFE5A3')
        for iid, row in zip(tree.get_children(), values):
            if row[0] == '합계':
                tree.item(iid, tags=('total',))
            elif row[-1] == '미완료':
                tree.item(iid, tags=('attention',))
        draw()

    def reset():
        nonlocal loaded, plot_rows
        loaded = False
        plot_rows = []
        tree.delete(*tree.get_children())
        for combo in (year_box, start_box):
            combo.configure(values=[])
        year.set('')
        start.set('전체')
        export_button.configure(state='disabled')
        note.set('차입금 원자료를 사용합니다.' if storage.is_file() else '자료 업로드에서 차입금 원자료를 선택하세요.')
        draw()

    def load():
        if task.busy or not storage.is_file():
            return

        def work():
            with uploaded_loan_sources(storage) as folder:
                yearly, quarterly, paths = loan_dashboard(folder)
                return yearly, quarterly, [Path(path).name for path in paths]

        def done(result):
            nonlocal annual, quarters, sources, loaded
            annual, quarters, sources = result
            years = list(quarters)
            year_box.configure(values=years)
            start_box.configure(values=['전체', *years])
            if start.get() not in years:
                start.set('전체')
            if year.get() not in years:
                year.set(report_year.get() if report_year.get() in years else years[-1] if years else '')
            loaded = True
            export_button.configure(state='normal' if years else 'disabled')
            render()
            status.set('차입금·이자 상환 분석을 불러왔습니다.')

        def failed(error):
            status.set('상환 자료를 읽지 못했습니다.')
            messagebox.showerror('상환 자료 확인', str(error), parent=window)

        task.run(work, done, failed)

    def export():
        if task.busy or not loaded or not quarters.get(year.get()):
            return
        path = target_file(window, None, '차입금 이자 상환')
        if not path:
            return
        rows = quarters[year.get()]
        chart_headers, chart_rows = plot_headers, plot_rows
        criteria, files = note.get(), sources

        def work():
            from openpyxl import Workbook
            from openpyxl.chart import LineChart, Reference
            from openpyxl.chart.label import DataLabelList
            from finance_data import append_row, format_sheet, save_atomic

            book = Workbook()
            try:
                details = book.active
                details.title = '분석'
                append_row(details, headers)
                for row in rows:
                    append_row(details, row)
                basis = book.create_sheet('분석 기준')
                append_row(basis, ['기준', criteria])
                for name in files:
                    append_row(basis, ['원본', name])
                data = book.create_sheet('그래프 데이터')
                append_row(data, chart_headers)
                for row in chart_rows:
                    append_row(data, row)
                for sheet in book:
                    format_sheet(sheet)
                if chart_rows:
                    chart = LineChart()
                    chart.title = '차입금·이자'
                    chart.y_axis.numFmt = '#,##0,,'
                    chart.y_axis.title = '백만원'
                    chart.dataLabels = DataLabelList(showVal=True, numFmt='#,##0,,')
                    chart.add_data(Reference(data, min_col=2, max_col=3, min_row=1, max_row=len(chart_rows)+1),
                                   titles_from_data=True)
                    chart.set_categories(Reference(data, min_col=1, min_row=2, max_row=len(chart_rows)+1))
                    data.add_chart(chart, 'J2')
                return save_atomic(book, path)
            finally:
                book.close()

        def failed(error):
            status.set('상환 분석 파일을 저장하지 못했습니다.')
            messagebox.showerror('Excel 저장', str(error), parent=window)

        task.run(work, lambda result: saved(window, status, open_file, result), failed)

    def selected(event=None):
        if notebook.select() == str(page) and not loaded:
            load()

    notebook.bind('<<NotebookTabChanged>>', selected, add='+')
    reset()
    return reset, selected
