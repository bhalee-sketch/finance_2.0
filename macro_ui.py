from check_list import CheckList
"""분류형 검증 도구의 공통 화면."""
from pathlib import Path
import queue
import threading
import qt_ui as tk
from qt_ui import ttk,filedialog,messagebox
from macro_reports import TITLES,FOLDERS,run_report
from ui_theme import dark_titlebar
from finance_accounts import load_finance_accounts


def open_macro(parent,desktop,center,open_file,kind):
    window=tk.Toplevel(parent);window.title(TITLES[kind]);dark_titlebar(window)
    center(window,760,min(650,window.winfo_screenheight()-90))
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    source=None;busy=False;messages=queue.Queue()
    from loading_ui import watch_loading
    catalog={};account_unit=tk.StringVar()
    catalog_path=desktop()/'settings'/'accountsforfinancecode.xlsx'
    status=tk.StringVar(value='원자료 Excel 파일을 선택하세요.')
    window._work_status=status
    watch_loading(window,status,lambda:busy)
    filename=tk.StringVar(value='선택한 자료 없음');mode=tk.StringVar(value='교비비등록금');exclude=tk.BooleanVar(value=False)
    footer=ttk.Frame(frame);footer.pack(side='bottom',fill='x',pady=(12,0))
    ttk.Label(footer,textvariable=status,wraplength=700,style='Muted.TLabel').pack(anchor='w',pady=8)
    def close():
        if not busy:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    def poll():
        nonlocal busy
        try:success,result=messages.get_nowait()
        except queue.Empty:window.after(100,poll);return
        busy=False;button.configure(state='normal');choose.configure(state='normal')
        if success:
            status.set(f'저장 완료: {result}')
            try:open_file(result)
            except Exception as e:messagebox.showwarning('저장 완료 · 자동 열기 실패',f'{result}\n{e}',parent=window)
        else:
            status.set('자료 확인 필요');messagebox.showerror('처리 중단',str(result),parent=window)
    def execute():
        nonlocal busy
        if source is None:messagebox.showinfo('자료 선택','먼저 원자료를 선택하세요.',parent=window);return
        options={'mode':mode.get(),'exclude_unpaid':exclude.get()}
        if kind=='expense':
            options['accounts']=[box.get(i) for i in box.curselection()]
            options['account_unit']=account_unit.get()
            try:
                current=load_finance_accounts(catalog_path)
                if any(a not in current.get(account_unit.get(),[]) for a in options['accounts']):
                    raise ValueError('계좌 목록이 변경되었습니다. 목록 새로고침 후 다시 선택하세요.')
            except Exception as e:
                messagebox.showerror('계좌 목록 확인',str(e),parent=window);return
            if not options['accounts']:messagebox.showinfo('계좌 선택','계좌를 하나 이상 선택하세요.',parent=window);return
        selected=source;busy=True;button.configure(state='disabled');choose.configure(state='disabled');status.set('자료를 분류하고 결과를 저장하는 중…')
        def work():
            try:messages.put((True,run_report(selected,kind,**options)))
            except Exception as e:messages.put((False,e))
        threading.Thread(target=work,daemon=True).start();window.after(100,poll)
    button=ttk.Button(footer,text='결과 생성 · 저장 후 열기  →',command=execute,style='Primary.TButton');button.pack(fill='x')
    ttk.Label(frame,text=TITLES[kind],style='Section.TLabel').pack(anchor='w',pady=(0,12))
    line=ttk.Frame(frame);line.pack(fill='x')
    ttk.Label(line,textvariable=filename,wraplength=490).pack(side='left')
    folder=desktop()/'settings'/FOLDERS[kind]
    def load(path):
        nonlocal source
        source=None;filename.set('선택한 자료 없음')
        try:
            source=Path(path);filename.set(source.name);status.set('준비 완료 · 결과는 바탕화면의 검증결과 폴더에 저장됩니다.')
        except Exception as e:status.set('자료 확인 필요');messagebox.showerror('자료 확인',str(e),parent=window)
    def browse():
        p=filedialog.askopenfilename(parent=window,initialdir=str(folder if folder.exists() else desktop()/'settings'),filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
        if p:load(p)
    choose=ttk.Button(line,text='자료 선택',command=browse);choose.pack(side='right')
    if kind=='expense':
        unit_line=ttk.Frame(frame);unit_line.pack(fill='x',pady=10)
        ttk.Label(unit_line,text='회계단위').pack(side='left',padx=(0,8))
        units=ttk.Combobox(unit_line,textvariable=account_unit,state='readonly',width=22)
        units.pack(side='left')
        def show_accounts(*_):
            box.delete(0,'end')
            for name in catalog.get(account_unit.get(),[]):box.insert('end',name)
            box.selection_set(0,'end')
        def refresh_accounts():
            nonlocal catalog
            if busy:return
            try:
                catalog=load_finance_accounts(catalog_path)
                units.configure(values=list(catalog))
                if account_unit.get() not in catalog:account_unit.set(next(iter(catalog)))
                show_accounts();status.set('계좌 목록 로드 완료 · 원장 자료와 처리할 계좌를 선택하세요.')
            except Exception as e:
                catalog={};units.configure(values=[]);account_unit.set('');box.delete(0,'end')
                status.set('settings/accountsforfinancecode.xlsx 파일을 확인하세요.')
                messagebox.showerror('계좌 목록 확인',str(e),parent=window)
        units.bind('<<ComboboxSelected>>',show_accounts)
        ttk.Button(unit_line,text='목록 새로고침',command=refresh_accounts).pack(side='right')
        ttk.Label(frame,text='설정 파일에 등록된 계좌 · 처리할 계좌를 선택하세요.',style='Muted.TLabel').pack(anchor='w')
        actions=ttk.Frame(frame);actions.pack(fill='x')
        ttk.Button(actions,text='전체 선택',command=lambda:box.selection_set(0,'end')).pack(side='left')
        ttk.Button(actions,text='선택 해제',command=lambda:box.selection_clear(0,'end')).pack(side='left',padx=8)
        body=ttk.Frame(frame);body.pack(fill='both',expand=True,pady=8)
        box=CheckList(body,selectmode='multiple',exportselection=False,height=7,relief='flat')
        scroll=ttk.Scrollbar(body,command=box.yview);box.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');box.pack(fill='both',expand=True)
    elif kind=='donation':
        ttk.Label(frame,text='회계 구분').pack(anchor='w',pady=(22,8))
        ttk.Combobox(frame,textvariable=mode,values=['교비비등록금','대학원비등록금'],state='readonly').pack(fill='x')
        ttk.Label(frame,text='출연받은재산 사용내역의 기본엑셀 다운로드 자료를 사용합니다.\n잔액(P열)이 있는 행을 유형별로 분류하고 합계를 계산합니다.',wraplength=690,style='Muted.TLabel').pack(anchor='w',pady=20)
    else:
        ttk.Checkbutton(frame,text='미지급금 · 각종세금예수금 · 가수금 제외',variable=exclude).pack(anchor='w',pady=24)
        ttk.Label(frame,text='임의 연구 · 건축 · 장학 · 기타 재원으로 분류합니다.\n차변 합계와 미분류·제외 건수를 결과에서 확인하세요.',style='Muted.TLabel').pack(anchor='w')
    if kind=='expense':window.after(50,refresh_accounts)
    candidates=sorted(p for p in folder.glob('*') if p.suffix.lower() in ('.xls','.xlsx','.xlsm') and not p.name.startswith('~$')) if folder.is_dir() else []
    if len(candidates)==1:window.after(100,lambda:load(candidates[0]))
