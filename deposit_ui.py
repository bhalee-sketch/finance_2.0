"""정기예금 해지계획 입력 화면."""
from datetime import date
from pathlib import Path
import re
import shutil
import sqlite3
from numeric_tree import NumericTreeview
import qt_ui as tk
from qt_ui import ttk, filedialog, messagebox
from deposit_plan import find_catalog, read_catalog, plan_entry, save_plan, period, load_drafts, save_drafts
from account_verifier import account_key
from ui_theme import dark_titlebar
from verifier import number
from deposit_search import search_catalog,resolve_catalog
from fixed_deposit_database import DATABASE as FIXED_DATABASE,load_fixed_accounts,import_fixed_accounts,store_fixed_accounts
from deposit_accounts import DATABASE as REGULAR_DATABASE,load_accounts,import_accounts,store_accounts


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
    folder=Path(root.get())
    fixed_database=folder/'fixed_accounts.sqlite3'
    regular_database=folder/'regular_accounts.sqlite3'
    today=date.today()
    draft_path=folder/'drafts.json'
    draft_error=None
    try:last_period,drafts=load_drafts(draft_path)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        draft_error=exc;last_period=None;drafts={}
    y,m=last_period or (today.year,today.month)
    year=tk.StringVar(value=str(y));month=tk.StringVar(value=str(m))
    processing=tk.StringVar(value=f'{y}-{m:02}-01' if last_period else today.isoformat())
    line=ttk.Frame(frame);line.pack(fill='x',pady=(0,10))
    ttk.Label(line,text='연도').pack(side='left')
    year_box=ttk.Combobox(line,textvariable=year,values=list(range(today.year+5,today.year-11,-1)),width=6)
    year_box._q.setAccessibleName('연도')
    year_box._q.setInsertPolicy(tk.W.QComboBox.InsertPolicy.NoInsert)
    year_box._q.setValidator(tk.G.QIntValidator(1900,9999,year_box._q))
    year_box._q.lineEdit().setStyleSheet('background: transparent; border: none; padding: 0;')
    year_box.pack(side='left',padx=8)
    ttk.Label(line,text='월').pack(side='left')
    month_box=ttk.Combobox(line,textvariable=month,values=list(range(1,13)),width=4,state='readonly')
    month_box._q.setAccessibleName('월')
    month_box.pack(side='left',padx=8)
    # Reserve the footer before laying out the expanding account panes.
    footer.pack(side='bottom',fill='x',pady=(8,0))
    body.pack(fill='both',expand=True)
    body.columnconfigure(0,weight=4,uniform='panes');body.columnconfigure(1,weight=5,uniform='panes');body.rowconfigure(0,weight=1)
    left=ttk.Frame(body);left.grid(row=0,column=0,sticky='nsew',padx=(0,20))
    right=ttk.Frame(body);right.grid(row=0,column=1,sticky='nsew')
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
    def refresh_options():
        nonlocal foptions,roptions
        foptions={f"{v['account']} · {v['bank']} · {v['name']}":k for k,v in sorted(fixed.items())}
        roptions={f"{v['account']} · {v['bank']} · {v['name']}":k for k,v in sorted(regular.items())}
        fbox.configure(values=list(foptions));dbox.configure(values=list(roptions))
        obox.configure(values=['원금과 같은 계좌',*roptions])
        if fvalue.get() not in foptions:fvalue.set('')
        if dest.get() not in roptions:dest.set('')
        if other.get() not in roptions:other.set('원금과 같은 계좌')
        counts.set(f'정기 {len(fixed)}개 · 원금 이체계좌 {len(regular)}개')
        show_principal()

    def load():
        def work():
            catalogs=[];notes=[]
            for is_fixed,local,bundled,read_db in (
                (True,fixed_database,FIXED_DATABASE,load_fixed_accounts),
                (False,regular_database,REGULAR_DATABASE,load_accounts),
            ):
                try:
                    source=local if local.exists() else bundled if bundled.exists() else find_catalog(folder,is_fixed)
                    catalogs.append(read_db(source) if source.suffix.lower()=='.sqlite3' else read_catalog(source,is_fixed))
                except (ValueError,OSError,sqlite3.Error) as exc:
                    catalogs.append({});notes.append(str(exc))
            return catalogs,notes
        def done(result):
            nonlocal fixed,regular
            (fixed,regular),notes=result
            refresh_options()
            status.set('계좌와 금액을 입력하고 목록에 추가하세요.' if not notes
                       else '계좌 추가에서 누락된 계좌 목록을 등록하세요.')
            if entries:status.set(f'저장된 해지 목록 {len(entries)}건을 불러왔습니다.')
            if draft_error:status.set('저장된 해지 목록을 읽을 수 없습니다.')
            if notes:messagebox.showwarning('계좌정보 확인','\n'.join(notes),parent=window)
        reader.run(work,done,failed)

    def failed(exc):
        status.set('계좌 목록을 저장하지 못했습니다.')
        messagebox.showerror('계좌정보 확인',str(exc),parent=window)

    def manage_accounts():
        if reader.busy:return
        dialog=tk.Toplevel(window);dialog.title('계좌 추가');dialog.transient(window)
        center(dialog,520,365);dark_titlebar(dialog);dialog.grab_set()
        form=ttk.Frame(dialog,padding=16);form.pack(fill='both',expand=True)
        kind=tk.StringVar(value='정기예금 계좌')
        kind_box=ttk.Combobox(form,textvariable=kind,values=['정기예금 계좌','이체 계좌'],state='readonly')
        kind_box._q.setAccessibleName('계좌 종류');kind_box.pack(fill='x',pady=(0,8))
        fields={};fixed_fields=ttk.Frame(form)
        for key,title in [('account','계좌번호'),('bank','은행명'),('name','계좌명'),('unit','회계단위'),('principal','원금')]:
            container=ttk.Frame(form if key in ('account','bank','name') else fixed_fields)
            container.pack(fill='x',pady=3)
            ttk.Label(container,text=title,width=10).pack(side='left')
            field=tk.StringVar();fields[key]=field
            entry=ttk.Entry(container,textvariable=field);entry._q.setAccessibleName(title);entry.pack(side='left',fill='x',expand=True)
        fixed_fields.pack(fill='x')
        def sync(_=None):
            if kind.get()=='정기예금 계좌':fixed_fields.pack(fill='x',before=buttons)
            else:fixed_fields.pack_forget()
        def saved(is_fixed,catalog,message):
            nonlocal fixed,regular
            if is_fixed:fixed=catalog
            else:regular=catalog
            refresh_options();status.set(message)
        def add_account():
            is_fixed=kind.get()=='정기예금 계좌'
            try:
                item={key:fields[key].get().strip() for key in ('account','bank','name')}
                key=account_key(item['account'])
                if not key or not re.fullmatch(r'[0-9 -]+',item['account']):
                    raise ValueError('계좌번호는 숫자와 하이픈으로 입력하세요.')
                if not item['bank'] or not item['name']:raise ValueError('은행명과 계좌명을 입력하세요.')
                if is_fixed:
                    item['unit']=fields['unit'].get().strip()
                    item['principal']=number(fields['principal'].get())
                    if not item['unit'] or item['principal']<=0:raise ValueError('회계단위와 0원보다 큰 원금을 입력하세요.')
                catalog=dict(fixed if is_fixed else regular)
                if key in catalog:raise ValueError('이미 등록된 계좌번호입니다.')
                catalog[key]=item
            except ValueError as exc:
                messagebox.showwarning('계좌 입력 확인',str(exc),parent=dialog);return
            dialog.destroy()
            def work():
                if is_fixed:store_fixed_accounts(fixed_database,catalog,'개별 등록')
                else:store_accounts(regular_database,catalog,'개별 등록',replace=True)
            reader.run(work,lambda _:saved(is_fixed,catalog,'계좌를 추가했습니다.'),failed)
        def upload():
            if entries:
                messagebox.showwarning('계좌 목록 교체','작성 중인 해지 항목을 모두 삭제한 뒤 계좌 목록을 교체하세요.',parent=dialog);return
            is_fixed=kind.get()=='정기예금 계좌'
            source=filedialog.askopenfilename(parent=dialog,title=f'{kind.get()} 목록 선택',filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
            if not source:return
            if not messagebox.askyesno('계좌 목록 교체',f'현재 {kind.get()} 목록을 선택한 Excel 파일로 교체할까요?',parent=dialog):return
            dialog.destroy()
            def work():
                if not is_fixed:
                    report=import_accounts(source,regular_database,replace=True)
                    return load_accounts(regular_database),report
                report=import_fixed_accounts(source,fixed_database)
                archive=folder/'originals'
                try:
                    archive.mkdir(parents=True,exist_ok=True)
                    target=archive/(report['sha256'][:16]+'-'+Path(source).name)
                    if not target.exists():shutil.copy2(source,target)
                except OSError:pass  # The validated account snapshot is already stored.
                return load_fixed_accounts(fixed_database),report
            def done(result):
                catalog,report=result
                if is_fixed:window._latest_fixed_import=report
                saved(is_fixed,catalog,f'Excel로 계좌 목록을 교체했습니다. ({len(catalog)}개)')
            reader.run(work,done,failed)
        buttons=ttk.Frame(form);buttons.pack(fill='x',pady=(12,4))
        ttk.Button(buttons,text='Excel 업로드로 목록 교체',command=upload).pack(side='left')
        ttk.Button(buttons,text='추가',command=add_account,style='Primary.TButton').pack(side='right')
        kind_box.bind('<<ComboboxSelected>>',sync)
        ttk.Label(form,text='정기예금 Excel은 회계단위와 원금 열도 필요합니다.',style='Muted.TLabel').pack(anchor='w',pady=(4,0))

    ttk.Button(line,text='계획표 생성',command=lambda:generate(),style='Primary.TButton').pack(side='right')
    ttk.Button(line,text='계좌 추가',command=manage_accounts).pack(side='right',padx=(0,8))
    ttk.Label(left,text='출금할 정기예금 계좌').pack(anchor='w')
    fbox=ttk.Combobox(left,textvariable=fvalue,state='normal');fbox.pack(fill='x',pady=4)
    fbox._q.setAccessibleName('출금할 정기예금 계좌')
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
    dbox._q.setAccessibleName('원금 이체 계좌');obox._q.setAccessibleName('이자 이체 계좌')
    def attach_search(box,var,is_fixed=False,allow_same=False):
        box._q.setCompleter(None)
        def candidates():
            catalog=fixed if is_fixed else regular
            options=foptions if is_fixed else roptions
            keys=list(catalog) if not var.get().strip() or var.get() in options or (allow_same and var.get()=='원금과 같은 계좌') else search_catalog(catalog,var.get())
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
                if event is not None and getattr(event,'keysym','')=='Return':
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
        input_box=ttk.Entry(grid,textvariable=var,width=16);input_box._q.setAccessibleName(label)
        input_box.grid(row=row+1,column=column,sticky='ew',padx=4,pady=(3,10))
        if var is not processing:input_box._q.setAlignment(tk.C.Qt.AlignmentFlag.AlignRight)
    ttk.Label(right,textvariable=summary,style='Accent.TLabel').pack(anchor='w',pady=(0,10))
    table=ttk.Frame(right);table.pack(fill='both',expand=True)
    tree=NumericTreeview(table,columns=('account','principal','net','date'),show='headings',height=9,selectmode='browse')
    for col,label,width in [('account','출금계좌',160),('principal','원금',115),('net','세후이자',105),('date','처리일',100)]:
        tree.heading(col,text=label);tree.column(col,width=width,minwidth=75,anchor='e' if col in ('principal','net') else 'w')
    def row_values(entry):
        return (entry['fixed']['account'],f"{entry['fixed']['principal']:,.0f}",
                f"{entry['gross']-entry['corp']-entry['local']:,.0f}",entry['date'].isoformat())

    def save_entries(updated):
        nonlocal drafts,entries
        if draft_error:raise ValueError(f'저장된 작업 내역을 읽을 수 없습니다. {draft_error}')
        y,m=period(year.get(),month.get())
        snapshot={**drafts,f'{y}-{m:02}':list(updated.values())}
        save_drafts(draft_path,(y,m),snapshot)
        drafts=snapshot;entries=updated
        summary.set(f'해지 목록 · {len(entries)}건')

    def show_draft(reset_input=False):
        nonlocal entries,counter
        try:y,m=period(year.get(),month.get())
        except ValueError:return
        if reset_input:
            processing.set(f'{y}-{m:02}-01')
            for field in (gross,corp,local):field.set('')
        tree.delete(*tree.get_children())
        records=drafts.get(f'{y}-{m:02}',[])
        entries={str(i):entry for i,entry in enumerate(records,1)}
        counter=len(entries)
        for iid,entry in entries.items():tree.insert('','end',iid=iid,values=row_values(entry))
        summary.set(f'해지 목록 · {len(entries)}건')

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
            save_entries({**entries,iid:entry})
            values=row_values(entry)
            if replace:tree.item(iid,values=values)
            else:tree.insert('', 'end',iid=iid,values=values)
            summary.set(f'해지 목록 · {len(entries)}건')
            status.set('해지 목록을 자동 저장했습니다.')
        except (OSError,ValueError,KeyError) as e:messagebox.showwarning('입력 확인',str(e),parent=window)
    def select_entry(_):
        sel=tree.selection()
        if not sel:return
        e=entries.get(sel[0])
        if not e:return
        def display_account(options,account):
            key=account_key(account['account'])
            return next((label for label,value in options.items() if value==key),account['account'])
        fvalue.set(display_account(foptions,e['fixed']))
        dest.set(display_account(roptions,e['destination']))
        other.set(display_account(roptions,e['interest_destination']) if e['interest_destination'] else '원금과 같은 계좌')
        gross.set(str(e['gross']));corp.set(str(e['corp']));local.set(str(e['local']));processing.set(e['date'].isoformat());show_principal()
    tree.bind('<<TreeviewSelect>>',select_entry)
    from check_list import tree_checks
    checked_entries=tree_checks(tree,centered=True)
    def delete():
        selected=set(checked_entries())
        if not selected:return
        try:save_entries({iid:entry for iid,entry in entries.items() if iid not in selected})
        except (OSError,ValueError) as exc:
            messagebox.showerror('해지 목록 저장 실패',str(exc),parent=window);return
        tree.delete(*selected)
        status.set('선택 항목을 삭제하고 해지 목록을 자동 저장했습니다.')
    buttons=ttk.Frame(left);buttons.pack(fill='x',pady=6)
    ttk.Button(buttons,text='목록에 추가  →',command=add,style='Primary.TButton').pack(side='left',fill='x',expand=True)
    ttk.Button(buttons,text='선택 항목 수정',command=lambda:add(True)).pack(side='right',padx=(8,0))
    list_scroll=ttk.Scrollbar(table,orient='vertical',command=tree.yview)
    tree.configure(yscrollcommand=list_scroll.set)
    list_scroll.pack(side='right',fill='y');tree.pack(side='left',fill='both',expand=True)
    actions=ttk.Frame(right);actions.pack(fill='x',pady=(8,0))
    ttk.Label(actions,text='목록을 선택하면 왼쪽에서 수정할 수 있습니다.',style='Muted.TLabel').pack(side='left')
    ttk.Button(actions,text='체크 항목 삭제',command=delete).pack(side='right')
    ttk.Separator(footer).pack(fill='x',pady=(0,4))
    ttk.Label(footer,textvariable=status,style='Muted.TLabel',wraplength=740).pack(fill='x')
    def generate():
        if reader.busy:return
        snapshot=(root.get(),year.get(),month.get(),list(entries.values()))
        def done(path):
            status.set('해지계획표를 저장했습니다. 결과 파일을 엽니다.')
            try:open_file(path)
            except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{path}\n\n{e}',parent=window)
        def failed(error):
            status.set('계획표 생성 실패');messagebox.showerror('계획표 생성 실패',str(error),parent=window)
        reader.run(lambda:save_plan(*snapshot),done,failed)
    show_draft()
    year.trace_add('write',lambda *_:show_draft(reset_input=True))
    month.trace_add('write',lambda *_:show_draft(reset_input=True))
    window.after(100,load)
