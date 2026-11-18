"""차입금 관리 화면."""
from datetime import date

import qt_ui as tk
from qt_ui import messagebox, ttk

from background_read import BackgroundRead
from finance_ui import apply_widths, content_widths, fill
from loan_manager import build_bundled_loan_report, save_loan_report, target_year
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
    ttk.Label(line, text='조회 연도').pack(side='left')
    ttk.Spinbox(line, from_=1900, to=9999, textvariable=year, width=8).pack(side='left', padx=10)

    status = tk.StringVar(value='조회 연도를 선택하고 생성을 누르세요.')
    window._work_status = status
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

    report = None
    exported_path = None

    def clear_report(*_):
        nonlocal report, exported_path
        if report is not None:
            report.close()
            report = None
        exported_path = None
        excel_button.configure(state='disabled')
        results.pack_forget()
        status.set('조회 연도를 선택하고 생성을 누르세요.')

    def execute():
        try:
            selected_year = target_year(year.get())
        except ValueError as error:
            messagebox.showwarning('입력 확인', str(error), parent=window)
            return

        def show_report(workbook):
            nonlocal report
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
            results.pack(fill='both', expand=True, pady=(6, 0))
            results.select(0)
            excel_button.configure(state='normal')
            status.set(f'{selected_year}년 조회 결과를 생성했습니다.')

        def failed(error):
            status.set('차입금 자료를 집계하지 못했습니다.')
            messagebox.showerror('집계 중단', str(error), parent=window)

        if not task.busy:
            clear_report()
            task.run(lambda: build_bundled_loan_report(selected_year), show_report, failed)

    def open_excel():
        if report is None or task.busy:
            return

        def open_saved(path):
            nonlocal exported_path
            exported_path = path
            status.set(f'보고서 저장 완료 · {path}')
            try:
                open_file(path)
            except Exception as error:
                messagebox.showwarning('저장 완료 · 열기 실패', f'{path}\n\n{error}', parent=window)

        def failed(error):
            status.set('Excel 파일을 저장하지 못했습니다.')
            messagebox.showerror('Excel 저장', str(error), parent=window)

        if exported_path is not None and exported_path.is_file():
            open_saved(exported_path)
        else:
            snapshot = report
            task.run(lambda: save_loan_report(snapshot), open_saved, failed)

    excel_button = ttk.Button(line, text='엑셀 열기', command=open_excel, state='disabled')
    excel_button.pack(side='right')
    ttk.Button(line, text='생성', command=execute, style='Primary.TButton').pack(side='right', padx=(0, 8))
    year.trace_add('write', clear_report)

    def close_report(event):
        if report is not None:
            report.close()

    window.bind('<Destroy>', close_report, add='+')
