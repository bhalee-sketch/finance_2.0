"""분류형 검증 도구의 공통 화면."""
from decimal import Decimal
from itertools import islice
from pathlib import Path

from openpyxl.utils import get_column_letter

import qt_ui as tk
from qt_ui import ttk, filedialog, messagebox
from background_read import BackgroundRead
from check_list import CheckList
from finance_accounts import load_finance_accounts
from macro_reports import TITLES, FOLDERS, build_report, save_report
from statement_catalog import amount_text
from statement_ui import table
from ui_theme import dark_titlebar


def centered_row(parent):
    row = ttk.Frame(parent)
    layout = tk.W.QHBoxLayout(row._q)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    def add(widget, stretch=0):
        layout.addWidget(widget._q, stretch, tk.C.Qt.AlignmentFlag.AlignVCenter)
        widget._q.show()
        return widget

    return row, layout, add


def select_accounts(window, center, catalog_path, selection, apply):
    try:
        catalog = load_finance_accounts(catalog_path)
    except Exception as error:
        messagebox.showerror('계좌 목록 확인', str(error), parent=window)
        return

    dialog = tk.Toplevel(window)
    dialog.title('처리계좌 선택')
    dialog.transient(window)
    center(dialog, 580, 540)
    content = ttk.Frame(dialog, padding=16)
    content.pack(fill='both', expand=True)
    row, layout, add = centered_row(content)
    row.pack(fill='x', pady=(0, 8))
    account_unit = tk.StringVar(value=selection[0] if selection[0] in catalog else next(iter(catalog)))
    chosen_by_unit = {selection[0]: set(selection[1])}
    active_unit = account_unit.get()
    add(ttk.Label(row, text='회계단위'))
    units = add(ttk.Combobox(row, textvariable=account_unit, values=list(catalog), state='readonly', width=22))
    layout.addStretch()
    add(ttk.Button(row, text='목록 새로고침', command=lambda: refresh()))

    ttk.Label(content, text='설정 파일에 등록된 계좌 · 처리할 계좌를 선택하세요.',
              style='Muted.TLabel').pack(anchor='w')
    actions = ttk.Frame(content)
    actions.pack(fill='x', pady=6)
    ttk.Button(actions, text='전체 선택', command=lambda: box.selection_set(0, 'end')).pack(side='left')
    ttk.Button(actions, text='선택 해제', command=lambda: box.selection_clear(0, 'end')).pack(side='left', padx=8)

    footer = ttk.Frame(content)
    footer.pack(side='bottom', fill='x', pady=(8, 0))
    ttk.Button(footer, text='선택 적용', command=lambda: confirm(), style='Primary.TButton').pack(side='right')
    ttk.Button(footer, text='취소', command=dialog.destroy).pack(side='right', padx=8)

    body = ttk.Frame(content)
    body.pack(fill='both', expand=True)
    box = CheckList(body, selectmode='multiple', exportselection=False, height=7)
    scroll = ttk.Scrollbar(body, command=box.yview)
    box.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    box.pack(fill='both', expand=True)

    def selected():
        return tuple(box.get(index) for index in box.curselection())

    def show_accounts():
        nonlocal active_unit
        active_unit = account_unit.get()
        names = catalog[active_unit]
        saved = chosen_by_unit.get(active_unit, names)
        box.delete(0, 'end')
        for index, name in enumerate(names):
            box.insert('end', name)
            if name in saved:
                box.selection_set(index)

    def change_unit(event):
        chosen_by_unit[active_unit] = set(selected())
        show_accounts()

    def refresh():
        nonlocal catalog
        try:
            refreshed = load_finance_accounts(catalog_path)
        except Exception as error:
            messagebox.showerror('계좌 목록 확인', str(error), parent=dialog)
            return
        chosen_by_unit[active_unit] = set(selected())
        catalog = refreshed
        units.configure(values=list(catalog))
        if active_unit not in catalog:
            account_unit.set(next(iter(catalog)))
        show_accounts()

    def confirm():
        accounts = selected()
        if not accounts:
            messagebox.showinfo('계좌 선택', '계좌를 하나 이상 선택하세요.', parent=dialog)
            return
        apply((active_unit, accounts))
        dialog.destroy()

    units.bind('<<ComboboxSelected>>', change_unit)
    show_accounts()
    dialog.grab_set()


def open_macro(parent, desktop, center, open_file, kind):
    window = tk.Toplevel(parent)
    window.title(TITLES[kind])
    dark_titlebar(window)
    center(window, 900, min(700, window.winfo_screenheight()-90))
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)

    settings = desktop()/'settings'
    folder = settings/FOLDERS[kind]
    catalog_path = settings/'accountsforfinancecode.xlsx'
    source = None
    selection = ('', ())
    report = None
    exported_path = None
    view_revision = 0
    status = tk.StringVar(value='원자료 Excel 파일을 선택하세요.')
    filename = tk.StringVar(value='선택한 자료 없음')
    mode = tk.StringVar(value='교비비등록금')
    exclude = tk.BooleanVar(value=False)
    expense_view = '확인 필요만'
    account_note = tk.StringVar(value='선택한 계좌 없음')
    window._work_status = status
    task = BackgroundRead(window, status)

    footer = ttk.Label(frame, textvariable=status, wraplength=700, style='Muted.TLabel')
    footer._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored, tk.W.QSizePolicy.Policy.Preferred)
    footer.pack(side='bottom', fill='x', pady=(8, 0))
    ttk.Label(frame, text=TITLES[kind], style='Section.TLabel').pack(anchor='w', pady=(0, 10))

    files, _, add_file = centered_row(frame)
    files.pack(fill='x', pady=(0, 6))
    file_label = ttk.Label(files, textvariable=filename)
    file_label._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored, tk.W.QSizePolicy.Policy.Preferred)
    add_file(file_label, stretch=1)
    add_file(ttk.Button(files, text='자료 선택', command=lambda: browse()))

    line, actions, add = centered_row(frame)
    line.pack(fill='x', pady=(0, 8))
    if kind == 'expense':
        add(ttk.Button(line, text='처리계좌 선택',
                       command=lambda: select_accounts(window, center, catalog_path, selection, apply_accounts)))
        view_choices = tk.W.QButtonGroup(line._q)
        for choice in ('확인 필요만', '전체보기'):
            option = add(ttk.Radiobutton(line, text=choice, variable=tk.StringVar(value=expense_view),
                                        value=choice, command=lambda chosen=choice: set_expense_view(chosen),
                                        style='Statement.TRadiobutton'))
            view_choices.addButton(option._q)
        label = ttk.Label(line, textvariable=account_note, style='Muted.TLabel')
        label._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored, tk.W.QSizePolicy.Policy.Preferred)
        add(label, stretch=1)
    elif kind == 'donation':
        add(ttk.Label(line, text='회계 구분'))
        add(ttk.Combobox(line, textvariable=mode, values=['교비비등록금', '대학원비등록금'],
                         state='readonly'))
        actions.addStretch()
    else:
        check = add(ttk.Checkbutton(line, text='미지급금 · 각종세금예수금 · 가수금 제외', variable=exclude))
        icon = (Path(__file__).resolve().parent/'assets'/'check.svg').as_posix()
        check._q.setStyleSheet(
            'QCheckBox::indicator {width:15px;height:15px;border:2px solid #827491;'
            'border-radius:3px;background:#FFFFFF;}'
            f'QCheckBox::indicator:checked {{background:#7651AD;image:url("{icon}");}}'
        )
        actions.addStretch()
    add(ttk.Button(line, text='결과 생성', command=lambda: execute(), style='Primary.TButton'))
    excel = add(ttk.Button(line, text='엑셀 열기', command=lambda: open_excel(), state='disabled'))

    preview = ttk.Frame(frame)
    tab_host = ttk.Frame(preview)
    tab_host.pack(fill='x')
    tab_layout = tk.W.QVBoxLayout(tab_host._q)
    tab_layout.setContentsMargins(0, 0, 0, 0)
    tabs = tk.WorkflowTabBar()
    tabs.setExpanding(False)
    tabs.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored, tk.W.QSizePolicy.Policy.Fixed)
    tab_layout.addWidget(tabs)
    tree = table(preview, [], auto_scroll=True, column_preferences=False)
    tree._q.setSortingEnabled(False)
    tree.proxy.sort(-1)

    def clear_report(*_):
        nonlocal report, exported_path, view_revision
        view_revision += 1
        if report is not None:
            report.close()
            report = None
        exported_path = None
        excel.configure(state='disabled')
        preview.pack_forget()
        tree.delete(*tree.get_children())
        status.set('결과 생성을 누르세요.' if source else '원자료 Excel 파일을 선택하세요.')

    def load(path):
        nonlocal source
        source = Path(path)
        filename.set(source.name)
        file_label._q.setToolTip(source.name)
        clear_report()

    def browse():
        path = filedialog.askopenfilename(parent=window, initialdir=str(folder if folder.exists() else settings),
                                          filetypes=[('Excel', '*.xls *.xlsx *.xlsm')])
        if path:
            load(path)

    def apply_accounts(chosen):
        nonlocal selection
        if chosen != selection:
            selection = chosen
            text = f'{selection[0]} · {len(selection[1])}개 계좌'
            account_note.set(text)
            label._q.setToolTip(text)
            clear_report()

    def show_sheet(index):
        nonlocal view_revision
        if report is None or index < 0:
            return
        view_revision += 1
        revision = view_revision
        sheet = report.worksheets[index]
        visible = [i for i in range(1, sheet.max_column+1)
                   if not getattr(sheet.column_dimensions.get(get_column_letter(i)), 'hidden', False)]
        columns = [str(i) for i in visible]
        tree.delete(*tree.get_children())
        tree.configure(columns=columns)
        for i, column in zip(visible, columns):
            header = sheet.cell(1, i).value or ''
            dimension = sheet.column_dimensions.get(get_column_letter(i))
            width = round(dimension.width*7) if dimension else 130
            tree.heading(column, text=header)
            tree.column(column, width=max(80, width), stretch=False,
                        anchor='e' if any(word in str(header) for word in ('금액', '잔액', '차변', '대변')) else 'w')
        rows = sheet.iter_rows(min_row=2, values_only=True) if sheet.max_row > 1 else iter(())

        def append_rows():
            if revision != view_revision or not tree.winfo_exists():
                return
            batch = list(islice(rows, 150))
            for values in batch:
                tree.insert('', 'end', values=[
                    '' if value is None else amount_text(value)
                    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool) else str(value)
                    for value in (values[i-1] for i in visible)
                ])
            if len(batch) == 150:
                tree.after(1, append_rows)

        append_rows()

    def show_report(workbook):
        nonlocal report
        report = workbook
        tabs.blockSignals(True)
        while tabs.count():
            tabs.removeTab(0)
        for sheet in report:
            tabs.addTab(sheet.title)
        first = next((i for i, sheet in enumerate(report.worksheets[1:], 1) if sheet.max_row > 1), 0)
        tabs.setCurrentIndex(first)
        tabs.blockSignals(False)
        preview.pack(fill='both', expand=True)
        show_sheet(first)
        excel.configure(state='normal')
        status.set('결과를 생성했습니다. 엑셀 열기를 누르면 저장 후 엽니다.')

    def execute():
        if task.busy:
            return
        if source is None:
            messagebox.showinfo('자료 선택', '먼저 원자료를 선택하세요.', parent=window)
            return
        unit, accounts = selection
        if kind == 'expense' and not accounts:
            messagebox.showinfo('계좌 선택', '처리계좌 선택에서 계좌를 하나 이상 선택하세요.', parent=window)
            return
        selected = source
        options = {'mode': mode.get(), 'exclude_unpaid': exclude.get()}
        if kind == 'expense':
            options.update(accounts=accounts, account_unit=unit, show_all=expense_view == '전체보기')

        def work():
            if kind == 'expense':
                current = load_finance_accounts(catalog_path)
                if any(account not in current.get(unit, ()) for account in accounts):
                    raise ValueError('계좌 목록이 변경되었습니다. 처리계좌 선택에서 다시 선택하세요.')
            return build_report(selected, kind, **options)

        def failed(error):
            status.set('자료 확인 필요')
            messagebox.showerror('처리 중단', str(error), parent=window)

        clear_report()
        task.run(work, show_report, failed)

    def open_excel():
        if report is None or task.busy:
            return

        def open_saved(path):
            nonlocal exported_path
            exported_path = path
            status.set(f'저장 완료: {path}')
            try:
                open_file(path)
            except Exception as error:
                messagebox.showwarning('저장 완료 · 열기 실패', f'{path}\n{error}', parent=window)

        def failed(error):
            status.set('Excel 파일을 저장하지 못했습니다.')
            messagebox.showerror('Excel 저장', str(error), parent=window)

        if exported_path is not None and exported_path.is_file():
            open_saved(exported_path)
        else:
            snapshot = report
            task.run(lambda: save_report(snapshot, kind), open_saved, failed)

    def set_expense_view(choice):
        nonlocal expense_view
        if choice != expense_view:
            expense_view = choice
            if report is not None:
                execute()

    tabs.currentChanged.connect(show_sheet)
    mode.trace_add('write', clear_report)
    exclude.trace_add('write', clear_report)
    window.bind('<Destroy>', lambda event: report.close() if report is not None else None, add='+')
    candidates = sorted(p for p in folder.glob('*') if p.is_file() and p.suffix.lower() in ('.xls', '.xlsx', '.xlsm')
                        and not p.name.startswith('~$'))
    if len(candidates) == 1:
        load(candidates[0])
