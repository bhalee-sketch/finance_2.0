"""차입금 관리 화면."""
from datetime import date
import threading
import queue
import qt_ui as tk
from qt_ui import ttk,filedialog,messagebox
from loan_manager import find_loan_files, generate_loans, target_year
from ui_theme import dark_titlebar


def open_loans(parent,desktop,center,open_file):
    window=tk.Toplevel(parent);window.title('차입금관리')
    width=min(800,window.winfo_screenwidth()-40)
    height=min(680,window.winfo_screenheight()-100)
    center(window,width,height);dark_titlebar(window)
    window.minsize(min(640,width),min(520,height))
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    # Reserve the action area before allocating space to the file list.
    footer=ttk.Frame(frame);footer.pack(side='bottom',fill='x',pady=(10,0))
    controls=ttk.Frame(frame);controls.pack(side='top',fill='x')
    ttk.Label(controls,text='차입금 관리',style='Section.TLabel').pack(anchor='w')
    ttk.Label(controls,text='상환 현황과 연도별·분기별 예정액을 확인하세요.',style='Muted.TLabel').pack(anchor='w',pady=(4,10))
    path=tk.StringVar(value=str(desktop()/'settings'/'loans'));year=tk.StringVar(value=str(date.today().year))
    ttk.Label(controls,text='차입금 원자료 폴더 (loans)').pack(anchor='w')
    path_row=ttk.Frame(controls);path_row.pack(fill='x',pady=6)
    ttk.Entry(path_row,textvariable=path).pack(side='left',fill='x',expand=True)
    def browse():
        p=filedialog.askdirectory(parent=window)
        if p:path.set(p);refresh()
    ttk.Button(path_row,text='폴더 변경',command=browse).pack(side='right',padx=(8,0))
    line=ttk.Frame(controls);line.pack(fill='x',pady=8)
    ttk.Label(line,text='조회 연도').pack(side='left')
    ttk.Spinbox(line,from_=1900,to=9999,textvariable=year,width=8).pack(side='left',padx=10)
    table=ttk.Frame(frame);table.pack(fill='both',expand=True,pady=(6,0))
    tree=ttk.Treeview(table,columns=('file',),show='headings',height=4)
    tree.heading('file',text='집계할 원자료 파일');tree.column('file',width=690)
    scrollbar=ttk.Scrollbar(table,orient='vertical',command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right',fill='y');tree.pack(side='left',fill='both',expand=True)
    status=tk.StringVar(value='원자료 파일 목록을 확인한 후 집계를 실행하세요.')
    window._work_status=status
    def refresh():
        tree.delete(*tree.get_children())
        try:
            files=find_loan_files(path.get())
            for p in files:tree.insert('','end',values=(p.name,))
            status.set(f'원자료 {len(files)}개 · 첫 번째 시트를 집계합니다.')
        except (ValueError,OSError) as e:
            status.set(str(e))
    ttk.Button(line,text='원자료 목록 새로고침',command=refresh).pack(side='right')
    ttk.Separator(footer).pack(fill='x',pady=(0,8))
    status_label=ttk.Label(footer,textvariable=status,wraplength=700,style='Muted.TLabel')
    status_label.pack(anchor='w',pady=(0,6))
    footer.bind('<Configure>',lambda e:status_label.configure(wraplength=max(200,e.width-10)))
    messages=queue.Queue();busy=False
    progress=ttk.Progressbar(footer,mode='indeterminate');progress.pack(fill='x',pady=4)
    def close():
        if not busy:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    def poll():
        nonlocal busy
        try:success,result=messages.get_nowait()
        except queue.Empty:window.after(100,poll);return
        busy=False;progress.stop();button.configure(state='normal')
        if success:
            status.set('보고서 저장 완료 · 결과 파일을 엽니다.')
            try:open_file(result)
            except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{result}\n\n{e}',parent=window)
        else:
            status.set('원자료 확인 필요');messagebox.showerror('집계 중단',result,parent=window)
    def execute():
        nonlocal busy
        try:y=target_year(year.get());find_loan_files(path.get())
        except (ValueError,OSError) as e:messagebox.showwarning('입력 확인',str(e),parent=window);return
        root=path.get();busy=True;button.configure(state='disabled');progress.start(15);status.set('차입금 자료를 집계하고 있습니다…')
        def work():
            try:messages.put((True,str(generate_loans(root,y))))
            except Exception as e:messages.put((False,str(e)))
        threading.Thread(target=work,daemon=True).start();window.after(100,poll)
    button=ttk.Button(footer,text='차입금 현황 · 상환예정표 생성  →',command=execute,style='Primary.TButton');button.pack(fill='x',pady=(6,0))
    window.after(100,refresh)
