"""차입금 관리 화면."""
from datetime import date

import qt_ui as tk
from qt_ui import filedialog, messagebox, ttk

from background_read import BackgroundRead
from finance_ui import apply_widths, content_widths, fill
from loan_manager import build_uploaded_loan_report, save_loan_report, target_year, upload_loan_sources
from loan_repayment_ui import install_repayment_tab
from result_paths import desktop_dir
from statement_ui import table
from ui_theme import dark_titlebar


def open_loans(parent, center, open_file):
    window = tk.Toplevel(parent)
    window.title('차입금관리')
    width = min(800, window.winfo_screenwidth()-40)
    height = min(680, window.winfo_screenheight()-100)
    center(window, width, height)
    dark_titlebar(window)
    window.minsize(min(640, width), min(520, height))

    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    footer = ttk.Frame(frame)
    footer.pack(side='bottom', fill='x', pady=(10, 0))
    controls = ttk.Frame(frame)
    controls.pack(side='top', fill='x')
    ttk.Label(controls, text='차입금 관리', style='Section.TLabel').pack(anchor='w')
    ttk.Label(controls, text='상환 현황과 연도별·분기별 예정액을 확인하세요.',
              style='Muted.TLabel').pack(anchor='w', pady=(4, 10))

    year = tk.StringVar(value=str(date.today().year))
    line = ttk.Frame(controls)
    line.pack(fill='x', pady=8)
    year_label = ttk.Label(line, text='조회 연도')
    year_label.pack(side='left')
    year_box = ttk.Spinbox(line, from_=1900, to=9999, textvariable=year, width=8)
    year_box._q.setKeyboardTracking(False)
    year_box.pack(side='left', padx=10)

    storage = desktop_dir()/'settings'/'loan-sources.zip'

    status = tk.StringVar()
    window._work_status = tk.StringVar()
    task = BackgroundRead(window, status)
    ttk.Separator(footer).pack(fill='x', pady=(0, 8))
    status_label = ttk.Label(footer, textvariable=status, wraplength=700, style='Muted.TLabel')
    status_label.pack(anchor='w')
    footer.bind('<Configure>', lambda event: status_label.configure(wraplength=max(200, event.width-10)))

    results = ttk.Notebook(frame)
    result_tables = {}
    for title in ('요약', '연도별현황', '분기별현황', '조회 연도 상환예정'):
        page = ttk.Frame(results)
        results.add(page, text=title)
        result_tables[title] = table(page, [], auto_scroll=True)
        if title == '요약':
            reset_repayment, load_repayment_if_selected = install_repayment_tab(
                results, window, storage, year, task, status, open_file
            )
    results.pack(fill='both', expand=True, pady=(6, 0))

    closing_view = None
    closing_page = None

    def update_work_status(*_):
        closing = closing_page is not None and results._q.currentWidget() is closing_page._q
        window._work_status.set(closing_view.caption.text() if closing else status.get())

    def show_context_controls():
        closing = closing_page is not None and results._q.currentWidget() is closing_page._q
        for control in (year_label, year_box, excel_button, status_label):
            control._q.setVisible(not closing)
        update_work_status()

    def show_closing_loans(data, selected_year, scope):
        nonlocal closing_view, closing_page
        if closing_view is None:
            from dashboard_loan_view import ClosingLoanView
            page = ttk.Frame(results)
            layout = tk.W.QVBoxLayout(page._q)
            closing_page = page
            closing_view = ClosingLoanView(storage)
            layout.addWidget(closing_view)
            results.add(page,text='결산 기준 차입금')
        results._q.setCurrentIndex(results._q.count()-1)
        closing_view.display(data, selected_year, scope)
        update_work_status()
    window.show_closing_loans = show_closing_loans
    report = None
    exported_path = None

    def clear_report(*_):
        nonlocal report, exported_path
        if report is not None:
            report.close()
            report = None
        exported_path = None
        excel_button.configure(state='disabled')
        for tree in result_tables.values():
            tree.delete(*tree.get_children())

    def upload():
        if task.busy:
            return
        paths = filedialog.askopenfilenames(
            parent=window, title='차입금 자료 갱신 · 전체 원자료 파일 선택', filetypes=[('Excel', '*.xls *.xlsx *.xlsm')]
        )
        if not paths:
            return

        def updated(_count):
            reset_repayment()
            if closing_view is not None:
                closing_view.refresh()
            execute()

        def failed(error):
            status.set('자료 갱신에 실패했습니다. 기존 자료를 사용합니다.')
            messagebox.showerror('차입금 자료 갱신 실패', str(error), parent=window)

        task.run(lambda: upload_loan_sources(paths, storage), updated, failed)

    def execute():
        if task.busy:
            refresh_timer.start(100)
            return
        refresh_timer.stop()
        try:
            selected_year = target_year(year.get())
        except ValueError as error:
            messagebox.showwarning('입력 확인', str(error), parent=window)
            return

        def show_report(workbook):
            nonlocal report
            if selected_year != target_year(year.get()):
                workbook.close()
                execute()
                return
            report = workbook
            for title, tree in result_tables.items():
                if title == '요약':
                    summary = workbook[title].iter_rows(max_col=2, values_only=True)
                    headers = next(summary)
                    rows = [(label, str(value) if label == '조회 연도' else value)
                            for label, value in summary if label not in ('자료 출처', '파일 수')]
                else:
                    sheet_name = title
                    if title == '조회 연도 상환예정':
                        sheet_name = f'{selected_year}년_분기별상환예정'
                    values = workbook[sheet_name].values
                    headers = next(values)
                    rows = list(values)
                numeric_start = 2 if title == '조회 연도 상환예정' else 1
                numeric_end = len(headers)-1 if headers[-1] == '상태' else len(headers)
                fill(tree, headers, rows, range(numeric_start, numeric_end))
                apply_widths(tree, content_widths(tree, headers, rows))
            excel_button.configure(state='normal')
            source = '갱신 자료' if storage.is_file() else '내장 자료'
            status.set(f'{selected_year}년 차입금 현황 · {source} {workbook["파일별현황"].max_row-1}개')
            load_repayment_if_selected()

        def failed(error):
            status.set('차입금 자료를 집계하지 못했습니다.')
            messagebox.showerror('집계 중단', str(error), parent=window)

        clear_report()
        task.run(lambda: build_uploaded_loan_report(storage, selected_year), show_report, failed)

    def open_excel():
        if report is None or task.busy or refresh_timer.isActive():
            return

        def open_saved(path):
            nonlocal exported_path
            exported_path = path
            status.set(f'보고서 저장 완료 · {path}')
            try:
                open_file(path)
            except Exception as error:
                messagebox.showwarning('저장 완료 · 열기 실패', f'{path}\n\n{error}', parent=window)
            load_repayment_if_selected()

        def failed(error):
            status.set('Excel 파일을 저장하지 못했습니다.')
            messagebox.showerror('Excel 저장', str(error), parent=window)

        if exported_path is not None and exported_path.is_file():
            open_saved(exported_path)
        else:
            snapshot = report
            task.run(lambda: save_loan_report(snapshot), open_saved, failed)

    ttk.Button(line, text='차입금 자료 갱신', command=upload).pack(side='left')
    excel_button = ttk.Button(line, text='엑셀 열기', command=open_excel, state='disabled')
    excel_button.pack(side='right')
    results._q.currentChanged.connect(show_context_controls)
    status.trace_add('write', update_work_status)
    refresh_timer = tk.C.QTimer(window._q)
    refresh_timer.setSingleShot(True)
    refresh_timer.timeout.connect(execute)

    def year_changed(*_):
        excel_button.configure(state='disabled')
        refresh_timer.start(180)

    year.trace_add('write', year_changed)
    refresh_timer.start(0)

    def close_report(event):
        if report is not None:
            report.close()

    window.bind('<Destroy>', close_report, add='+')
