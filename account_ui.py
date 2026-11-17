"""Two-file account balance verification with separate on-demand Excel export."""
from datetime import date
from pathlib import Path
import queue
import threading
import subprocess
import qt_ui as tk
from qt_ui import ttk,filedialog,messagebox
from account_verifier import run_account
from tax_result_view import TaxResultView
from result_paths import result_path
from ui_theme import dark_titlebar


def issue_sheets(workbook):
    result=workbook['검증결과'];rows=list(result.iter_rows(values_only=True))
    issues=[list(row) for row in rows[1:] if row[4]!='일치']
    sheets=[{'name':'계좌별 불일치','headers':list(rows[0]),'rows':issues}]
    if '자료확인' in workbook:
        notes=list(workbook['자료확인'].iter_rows(values_only=True))
        sheets.append({'name':'자료 확인','headers':list(notes[0]),'rows':[list(row) for row in notes[1:]]})
    return sheets


def open_account_view(parent,center,open_file):
    window=tk.Toplevel(parent,show_on_create=False);window.title('예금시재 계좌별 검증');dark_titlebar(window)
    center(window,1050,720)
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='예금시재 계좌별 검증',style='Section.TLabel').pack(anchor='w',pady=(0,12))
    cms=tk.StringVar();school=tk.StringVar();controls=[]
    def choose(variable,label,entry):
        selected=filedialog.askopenfilename(parent=window,title=label+' 선택',filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
        if selected:
            variable.set(selected);entry.set(Path(selected).name)
    for label,variable in [('CMS 파일',cms),('학사 파일',school)]:
        line=ttk.Frame(frame);line.pack(fill='x',pady=5)
        ttk.Label(line,text=label,width=10).pack(side='left')
        filename=tk.StringVar(value='파일을 선택하세요')
        entry=ttk.Entry(line,textvariable=filename,state='readonly',width=40)
        entry._q.setMaximumWidth(480);entry._q.setAccessibleName(label);entry.pack(side='left')
        def tooltip(*args,variable=variable,entry=entry):entry._q.setToolTip(variable.get())
        variable.trace_add('write',tooltip)
        select=ttk.Button(line,text='파일 선택',command=lambda v=variable,l=label,f=filename:choose(v,l,f))
        select.pack(side='left',padx=8);controls.append(select)
    actions=ttk.Frame(frame);actions.pack(fill='x',pady=(10,8))
    status=tk.StringVar(value='CMS 파일과 학사 파일을 선택한 뒤 검증을 실행하세요.')
    window._work_status=status
    ttk.Label(frame,textvariable=status,style='Muted.TLabel',wraplength=1000).pack(side='bottom',fill='x',pady=(8,0))
    results=TaxResultView(frame);window._account_results=results
    workbook=None;output=None;busy=False;messages=queue.Queue()
    def export():
        nonlocal output
        if busy or workbook is None:return
        try:
            if output is None or not output.exists():
                output=result_path('예금시재 계좌별 검증');workbook.save(output)
            open_file(output)
        except (OSError,subprocess.SubprocessError) as exc:messagebox.showerror('Excel 열기',str(exc),parent=window)
    def poll():
        nonlocal busy,workbook,output
        try:ok,value=messages.get_nowait()
        except queue.Empty:window.after(100,poll);return
        busy=False
        for control in controls:control.configure(state='normal')
        run_button.configure(state='normal')
        if ok:
            if workbook is not None:workbook.close()
            workbook,sheets=value;output=None
            results.set_results(sheets);excel_button.configure(state='normal')
            summary=dict(workbook['검증요약'].iter_rows(min_row=2,values_only=True))
            status.set(f"검증 완료 · 전체 {summary['전체 계좌']:,}계좌 · 일치 {summary['일치']:,} · 불일치 {summary['불일치']:,} · 자료 확인 {summary['자료 확인 건수']:,}건")
        else:
            status.set('자료 확인 필요');messagebox.showerror('검증 중단',str(value),parent=window)
    def execute():
        nonlocal busy
        if busy:return
        if not cms.get() or not school.get():
            messagebox.showinfo('파일 선택','CMS 파일과 학사 파일을 모두 선택하세요.',parent=window);return
        selected=(cms.get(),school.get())
        busy=True;run_button.configure(state='disabled');excel_button.configure(state='disabled')
        for control in controls:control.configure(state='disabled')
        results.clear();status.set('계좌별 잔액을 검증하고 있습니다…')
        def work():
            try:
                result=run_account('',date.today().isoformat(),*selected,save=False)
                messages.put((True,(result,issue_sheets(result))))
            except Exception as exc:messages.put((False,exc))
        threading.Thread(target=work,daemon=True).start();window.after(100,poll)
    run_button=ttk.Button(actions,text='검증 실행',command=execute,style='Primary.TButton');run_button.pack(side='right')
    excel_button=ttk.Button(actions,text='엑셀로 열기',command=export,state='disabled');excel_button.pack(side='right',padx=8)
    def close():
        if busy:return
        if workbook is not None:workbook.close()
        window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    window.deiconify()
    return window
