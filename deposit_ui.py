"""정기예금 해지계획 입력 화면."""
from datetime import date
from pathlib import Path
from numeric_tree import NumericTreeview
import qt_ui as tk
from qt_ui import ttk, filedialog, messagebox
from deposit_plan import find_catalog, read_catalog, plan_entry, save_plan, period
from account_verifier import account_key
from ui_theme import dark_titlebar
from deposit_search import search_catalog,resolve_catalog


def open_deposit(parent, desktop, center, open_file):
    window=tk.Toplevel(parent);window.title('정기예금 해지계획표')
    center(window,1120,700);dark_titlebar(window)
    window.minsize(1020,650)

    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    header=ttk.Frame(frame);header.pack(fill='x',pady=(0,12))
    ttk.Label(header,text='정기예금 해지계획표',style='Section.TLabel').pack(side='left')
    body=ttk.Frame(frame)
    footer=ttk.Frame(frame)
    root=tk.StringVar(value=str(desktop()/'settings'/'deposit plan'))
    fixed_path=tk.StringVar();regular_path=tk.StringVar()
    year=tk.StringVar(value=str(date.today().year));month=tk.StringVar(value=str(date.today().month))
    processing=tk.StringVar(value=date.today().isoformat())
    line=ttk.Frame(frame);line.pack(fill='x',pady=(0,10))
    ttk.Label(line,text='연도').pack(side='left');ttk.Spinbox(line,from_=1900,to=9999,textvariable=year,width=6).pack(side='left',padx=8)
    ttk.Label(line,text='월').pack(side='left');ttk.Combobox(line,textvariable=month,values=list(range(1,13)),width=4,state='readonly').pack(side='left',padx=8)
    def default_date(*_):
        try:y,m=period(year.get(),month.get());processing.set(f'{y}-{m:02}-01')
        except ValueError:pass
    year.trace_add('write',default_date);month.trace_add('write',default_date)
    def settings():
        if entries:
            messagebox.showwarning('자료 설정','작성 중인 항목을 모두 삭제한 뒤 계좌 자료를 변경할 수 있습니다.',parent=window)
            return
        dialog=tk.Toplevel(window);dialog.title('계좌 자료 설정')
        center(dialog,720,350);dark_titlebar(dialog);dialog.transient(window);dialog.grab_set()
        panel=ttk.Frame(dialog,padding=20);panel.pack(fill='both',expand=True)
        folder=tk.StringVar(value=root.get());fp=tk.StringVar(value=fixed_path.get());rp=tk.StringVar(value=regular_path.get())
        def browse_folder():
            selected=filedialog.askdirectory(parent=dialog)
            if selected:folder.set(selected);fp.set('');rp.set('')
        def browse_file(var):
            selected=filedialog.askopenfilename(parent=dialog,initialdir=folder.get(),filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
            if selected:var.set(selected)
        for label,var,command in [('기본 폴더',folder,browse_folder),('정기예금 파일',fp,lambda:browse_file(fp)),('보통예금 파일',rp,lambda:browse_file(rp))]:
            ttk.Label(panel,text=label).pack(anchor='w')
            row=ttk.Frame(panel);row.pack(fill='x',pady=(3,10))
            ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
            ttk.Button(row,text='변경',command=command).pack(side='right',padx=(8,0))
        ttk.Label(panel,text='파일을 지정하지 않으면 기본 폴더에서 자동으로 찾습니다.',style='Muted.TLabel').pack(anchor='w')
        def close():
            dialog.destroy()
        def apply():
            root.set(folder.get());fixed_path.set(fp.get());regular_path.set(rp.get());close();load()
        dialog.protocol('WM_DELETE_WINDOW',close)
        ttk.Button(panel,text='적용하고 불러오기',command=apply,style='Primary.TButton').pack(anchor='e',pady=12)
    ttk.Button(header,text='자료 설정',command=settings).pack(side='right')
    body.pack(fill='both',expand=True)
    body.columnconfigure(0,weight=4,uniform='panes');body.columnconfigure(1,weight=5,uniform='panes');body.rowconfigure(0,weight=1)
    left=ttk.Frame(body);left.grid(row=0,column=0,sticky='nsew',padx=(0,20))
    right=ttk.Frame(body);right.grid(row=0,column=1,sticky='nsew')
    footer.pack(fill='x',pady=(12,0))
    fixed={};regular={};foptions={};roptions={};entries={};counter=0
    fvalue=tk.StringVar();dest=tk.StringVar();other=tk.StringVar(value='원금과 같은 계좌')
    info=tk.StringVar(value='출금 계좌를 선택하면 원금이 표시됩니다.')
    counts=tk.StringVar(value='계좌정보 불러오는 중…')
    summary=tk.StringVar(value='해지 목록 · 0건')
    ttk.Label(line,textvariable=counts,style='Muted.TLabel').pack(side='left',padx=12)
    status=tk.StringVar(value='계좌 목록의 원금은 자동 반영됩니다. 이자와 세금은 직접 입력하세요.')
    window._work_status=status
    from background_read import BackgroundRead
    reader=BackgroundRead(window,status)
    def load():
        if reader.busy:return
        if entries:
            messagebox.showwarning('목록 확인','등록된 해지 항목을 모두 삭제한 후 계좌정보를 다시 불러오세요.',parent=window);return
        folder=root.get();fixed_name=fixed_path.get();regular_name=regular_path.get()
        def work():
            fp=Path(fixed_name) if fixed_name else find_catalog(folder,True)
            rp=Path(regular_name) if regular_name else find_catalog(folder,False)
            return fp,rp,read_catalog(fp,True),read_catalog(rp,False)
        def done(value):
            nonlocal fixed,regular,foptions,roptions
            fp,rp,f,r=value;fixed,regular=f,r
            foptions={f"{v['account']} · {v['bank']} · {v['name']}":k for k,v in f.items()}
            roptions={f"{v['account']} · {v['bank']} · {v['name']}":k for k,v in r.items()}
            fbox.configure(values=[]);dbox.configure(values=[]);obox.configure(values=['원금과 같은 계좌'])
            fvalue.set('');dest.set('');other.set('원금과 같은 계좌')
            fixed_path.set(str(fp));regular_path.set(str(rp))
            counts.set(f'정기 {len(f)}개 · 보통 {len(r)}개')
            info.set('출금 계좌를 선택하면 원금이 표시됩니다.')
            status.set('계좌와 금액을 입력하고 목록에 추가하세요.')
        def failed(exc):
            nonlocal fixed,regular,foptions,roptions
            fixed={};regular={};foptions={};roptions={}
            for box in (fbox,dbox):box.configure(values=[])
            obox.configure(values=['원금과 같은 계좌'])
            fvalue.set('');dest.set('');other.set('원금과 같은 계좌')
            info.set('계좌정보를 다시 불러오세요.');counts.set('계좌정보 확인 필요')
            status.set('자료 설정에서 계좌 파일을 확인한 후 다시 불러오세요.')
            messagebox.showerror('계좌정보 확인',str(exc),parent=window)
        reader.run(work,done,failed)
    ttk.Button(line,text='계좌 새로고침',command=load).pack(side='right')
    ttk.Label(left,text='출금할 정기예금 계좌').pack(anchor='w')
    fbox=ttk.Combobox(left,textvariable=fvalue,state='normal');fbox.pack(fill='x',pady=4)
    def show_principal(_=None):
        try:key=resolve_catalog(fixed,foptions,fvalue.get())
        except ValueError:key=None
        f=fixed.get(key)
        info.set(f"회계단위: {f['unit']}  |  원금: {f['principal']:,.0f}원" if f else '계좌를 선택하세요.')
    fbox.bind('<<ComboboxSelected>>',show_principal)
    ttk.Label(left,textvariable=info,wraplength=430,style='Accent.TLabel').pack(anchor='w',pady=4)
    ttk.Label(left,text='원금 이체 계좌').pack(anchor='w')
    dbox=ttk.Combobox(left,textvariable=dest,state='normal');dbox.pack(fill='x',pady=4)
    ttk.Label(left,text='이자 이체 계좌').pack(anchor='w')
    obox=ttk.Combobox(left,textvariable=other,state='normal',values=['원금과 같은 계좌']);obox.pack(fill='x',pady=4)
    def attach_search(box,var,is_fixed=False,allow_same=False):
        def candidates():
            catalog=fixed if is_fixed else regular
            options=foptions if is_fixed else roptions
            keys=search_catalog(catalog,var.get())
            values=[label for label,key in options.items() if key in keys]
            if allow_same:values=['원금과 같은 계좌']+values
            box.configure(values=values)
            return catalog,options
        def changed(event=None):
            candidates()
            if is_fixed:show_principal()
        def complete(event=None):
            catalog,options=candidates()
            if allow_same and var.get()=='원금과 같은 계좌':return
            try:
                key=resolve_catalog(catalog,options,var.get())
                var.set(next(label for label,value in options.items() if value==key))
            except ValueError:
                if event is not None and event.keysym=='Return':
                    box.event_generate('<Down>')
            if is_fixed:show_principal()
        box.configure(postcommand=candidates)
        box.bind('<KeyRelease>',changed)
        box.bind('<Return>',complete)
        box.bind('<FocusOut>',complete)
        box.bind('<<ComboboxSelected>>',complete)
    attach_search(fbox,fvalue,True)
    attach_search(dbox,dest)
    attach_search(obox,other,allow_same=True)
    ttk.Label(left,text='계좌명·코드 입력 후 Enter · 중복은 오른쪽 화살표로 선택',style='Muted.TLabel').pack(anchor='w',pady=3)
    gross=tk.StringVar();corp=tk.StringVar();local=tk.StringVar()
    grid=ttk.Frame(left);grid.pack(fill='x',pady=10)
    for c,(label,var) in enumerate([('세전이자',gross),('법인세',corp),('지방소득세',local),('처리예정일 (YYYY-MM-DD)',processing)]):
        column=c%2;row=(c//2)*2
        grid.columnconfigure(column,weight=1)
        ttk.Label(grid,text=label).grid(row=row,column=column,sticky='w',padx=4)
        ttk.Entry(grid,textvariable=var,width=16).grid(row=row+1,column=column,sticky='ew',padx=4,pady=(3,10))
    ttk.Label(right,textvariable=summary,style='Accent.TLabel').pack(anchor='w',pady=(0,10))
    table=ttk.Frame(right);table.pack(fill='both',expand=True)
    tree=NumericTreeview(table,columns=('account','principal','net','date'),show='headings',height=9,selectmode='browse')
    for col,label,width in [('account','출금계좌',160),('principal','원금',115),('net','세후이자',105),('date','처리일',100)]:
        tree.heading(col,text=label);tree.column(col,width=width,minwidth=75,anchor='w')
    def add(update=False):
        nonlocal counter
        try:
            selected=tree.selection()
            if update and not selected:raise ValueError('수정할 목록 항목을 선택하세요.')
            entry=plan_entry(fixed,regular,resolve_catalog(fixed,foptions,fvalue.get()),resolve_catalog(regular,roptions,dest.get()),None if other.get()=='원금과 같은 계좌' else resolve_catalog(regular,roptions,other.get()),gross.get(),corp.get(),local.get(),processing.get(),year.get(),month.get())
            key=account_key(entry['fixed']['account']);replace=selected[0] if update else None
            if any(account_key(e['fixed']['account'])==key and iid!=replace for iid,e in entries.items()):raise ValueError('이미 등록된 정기예금 계좌입니다.')
            if replace:iid=replace
            else:counter+=1;iid=str(counter)
            entries[iid]=entry
            values=(entry['fixed']['account'],f"{entry['fixed']['principal']:,.0f}",f"{entry['gross']-entry['corp']-entry['local']:,.0f}",entry['date'].isoformat())
            if replace:tree.item(iid,values=values)
            else:tree.insert('', 'end',iid=iid,values=values)
            summary.set(f'해지 목록 · {len(entries)}건')
            status.set('수정할 항목은 오른쪽 목록에서 선택하세요.')
        except (ValueError,KeyError) as e:messagebox.showwarning('입력 확인',str(e),parent=window)
    def select_entry(_):
        sel=tree.selection()
        if not sel:return
        e=entries[sel[0]]
        fvalue.set(next(k for k,v in foptions.items() if v==account_key(e['fixed']['account'])))
        dest.set(next(k for k,v in roptions.items() if v==account_key(e['destination']['account'])))
        other.set(next(k for k,v in roptions.items() if v==account_key(e['interest_destination']['account'])) if e['interest_destination'] else '원금과 같은 계좌')
        gross.set(str(e['gross']));corp.set(str(e['corp']));local.set(str(e['local']));processing.set(e['date'].isoformat());show_principal()
    tree.bind('<<TreeviewSelect>>',select_entry)
    from check_list import tree_checks
    checked_entries=tree_checks(tree)
    def delete():
        for iid in checked_entries():tree.delete(iid);entries.pop(iid,None)
        summary.set(f'해지 목록 · {len(entries)}건')
        status.set('선택 항목을 삭제했습니다.')
    buttons=ttk.Frame(left);buttons.pack(fill='x',pady=6)
    ttk.Button(buttons,text='목록에 추가  →',command=add,style='Primary.TButton').pack(side='left',fill='x',expand=True)
    ttk.Button(buttons,text='선택 항목 수정',command=lambda:add(True)).pack(side='right',padx=(8,0))
    list_scroll=ttk.Scrollbar(table,orient='vertical',command=tree.yview)
    tree.configure(yscrollcommand=list_scroll.set)
    list_scroll.pack(side='right',fill='y');tree.pack(side='left',fill='both',expand=True)
    actions=ttk.Frame(right);actions.pack(fill='x',pady=(8,0))
    ttk.Label(actions,text='목록을 선택하면 왼쪽에서 수정할 수 있습니다.',style='Muted.TLabel').pack(side='left')
    ttk.Button(actions,text='체크 항목 삭제',command=delete).pack(side='right')
    ttk.Separator(footer).pack(fill='x',pady=(0,10))
    ttk.Label(footer,textvariable=status,style='Muted.TLabel',wraplength=740).pack(side='left',fill='x',expand=True)
    def generate():
        try:
            path=save_plan(root.get(),year.get(),month.get(),list(entries.values()))
        except Exception as e:messagebox.showerror('계획표 생성 실패',str(e),parent=window);return
        status.set('해지계획표를 저장했습니다. 결과 파일을 엽니다.')
        try:open_file(path)
        except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{path}\n\n{e}',parent=window)
    ttk.Button(footer,text='계획표 생성  →',command=generate,style='Primary.TButton').pack(side='right',padx=(12,0))
    window.after(100,load)
