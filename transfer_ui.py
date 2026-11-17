"""계좌 검색 및 이번 실행에서 생성한 문구별 복사."""
from pathlib import Path
import qt_ui as tk
from qt_ui import ttk,filedialog,messagebox
from transfer_text import find_accounts,load_accounts,matches,make_text
from ui_theme import dark_titlebar,BG


def open_transfer(parent,desktop,center,open_file):
    window=tk.Toplevel(parent);window.title('자금이체 문구 생성')
    center(window,920,min(650,window.winfo_screenheight()-90));window.minsize(780,500)
    dark_titlebar(window)
    frame=ttk.Frame(window,padding=14);frame.pack(fill='both',expand=True)
    accounts=[];selected=[None,None];selected_file=None;lines=[]
    queries=[tk.StringVar(),tk.StringVar()];hints=[tk.StringVar(),tk.StringVar()]
    prefix=tk.StringVar(value='자금이체');status=tk.StringVar(value='계좌 자료를 불러오는 중…')
    window._work_status=status
    header=ttk.Frame(frame);header.pack(fill='x',pady=(0,12))
    ttk.Label(header,text='자금이체 문구 생성',style='Section.TLabel').pack(side='left')
    from background_read import BackgroundRead
    reader=BackgroundRead(window,status)
    def load(path=None):
        if reader.busy:return
        candidate=Path(path) if path else selected_file
        folder=desktop()/'settings'
        def work():
            chosen=candidate or find_accounts(folder)
            return chosen,load_accounts(chosen)
        def done(value):
            nonlocal accounts,selected_file
            selected_file,accounts=value
            for i in (0,1):search(i)
            status.set('계좌명 또는 끝 5자리를 입력하세요. 중복이면 계좌 선택 버튼으로 선택하세요.')
        def failed(exc):
            nonlocal accounts
            accounts=[]
            for i in (0,1):search(i)
            status.set('자료 설정에서 계좌 파일을 확인한 후 다시 불러오세요.')
            messagebox.showerror('계좌 자료 확인',str(exc),parent=window)
        reader.run(work,done,failed)
    def browse():
        path=filedialog.askopenfilename(parent=window,initialdir=str(desktop()/'settings'),filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
        if path:load(path)
    ttk.Button(header,text='자료 설정',command=browse).pack(side='right')
    ttk.Button(header,text='새로고침',command=load).pack(side='right',padx=8)
    form=ttk.Frame(frame);form.pack(fill='x');form.columnconfigure(1,weight=1)
    ttk.Label(form,text='문구 구분',width=12).grid(row=0,column=0,sticky='w',pady=5)
    ttk.Entry(form,textvariable=prefix).grid(row=0,column=1,sticky='ew',pady=5)
    ttk.Label(form,text='빈칸이면 계좌명만',style='Muted.TLabel').grid(row=0,column=2,padx=(10,0))
    def candidates(i):
        q=queries[i].get().strip()
        if not q:return []
        exact=[a for a in accounts if a['name'].casefold()==q.casefold()]
        return exact or matches(accounts,q)
    def search(i,*_):
        found=candidates(i);selected[i]=found[0] if len(found)==1 else None
        hints[i].set(f"{found[0]['name']} | {found[0]['number']}" if len(found)==1 else
                     (f'{len(found)}개 일치 · 계좌 선택 버튼으로 선택하세요.' if found else '계좌명 또는 끝 5자리를 입력하세요.'))
    def pick(i):
        found=candidates(i)
        if not found:messagebox.showinfo('계좌 검색','일치하는 계좌가 없습니다.',parent=window);return
        if len(found)==1:search(i);return
        dialog=tk.Toplevel(window);dialog.title('중복 계좌 선택');dark_titlebar(dialog)
        center(dialog,760,360);dialog.transient(window);dialog.grab_set()
        panel=ttk.Frame(dialog,padding=16);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='계좌명과 계좌번호를 확인하고 선택하세요.').pack(anchor='w',pady=(0,8))
        tree=ttk.Treeview(panel,columns=('name','number'),show='headings',selectmode='browse',height=7)
        tree.heading('name',text='전체 계좌명');tree.heading('number',text='계좌번호')
        tree.column('name',width=450);tree.column('number',width=210)
        controls=ttk.Frame(panel);controls.pack(side='bottom',fill='x',pady=8)
        scroll=ttk.Scrollbar(panel,command=tree.yview);scroll.pack(side='right',fill='y')
        tree.configure(yscrollcommand=scroll.set);tree.pack(fill='both',expand=True)
        for n,a in enumerate(found):tree.insert('','end',iid=str(n),values=(a['name'],a['number']))
        def close():dialog.destroy()
        def confirm(*_):
            if not tree.selection():return
            selected[i]=found[int(tree.selection()[0])]
            hints[i].set(f"{selected[i]['name']} | {selected[i]['number']}");close()
        ttk.Button(controls,text='선택',command=confirm,style='Primary.TButton').pack(side='right')
        tree.bind('<Double-1>',confirm);dialog.protocol('WM_DELETE_WINDOW',close)
    account_entries=[]
    for i,title in enumerate(('출금계좌','입금계좌')):
        r=1+i*2
        ttk.Label(form,text=title,width=12).grid(row=r,column=0,sticky='w',pady=5)
        entry=ttk.Entry(form,textvariable=queries[i]);entry.grid(row=r,column=1,sticky='ew',pady=5)
        account_entries.append(entry)
        entry.bind('<Return>',lambda e,index=i:pick(index))
        ttk.Button(form,text='계좌 선택',width=14,command=lambda index=i:pick(index)).grid(row=r,column=2,padx=(10,0),pady=5,sticky='ew')
        hint_frame=ttk.Frame(form,height=30);hint_frame.grid(row=r+1,column=1,columnspan=2,sticky='ew',pady=(0,6));hint_frame.pack_propagate(False)
        hint=ttk.Label(hint_frame,textvariable=hints[i],style='Muted.TLabel',wraplength=650);hint.pack(fill='x')
        hint_frame.bind('<Configure>',lambda e,label=hint:label.configure(wraplength=max(200,e.width)))
        queries[i].trace_add('write',lambda *_,index=i:search(index))
    actions=ttk.Frame(frame);actions.pack(fill='x',pady=10)
    footer=ttk.Frame(frame);footer.pack(side='bottom',fill='x',pady=(8,0))
    ttk.Label(footer,textvariable=status,wraplength=850,style='Muted.TLabel').pack(anchor='w')
    ttk.Label(frame,text='생성한 문구 · 창을 닫으면 목록이 사라집니다.',style='Accent.TLabel').pack(anchor='w',pady=5)
    area=ttk.Frame(frame);area.pack(fill='both',expand=True)
    canvas=tk.Canvas(area,bg=BG,highlightthickness=0);scroll=ttk.Scrollbar(area,command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
    content=ttk.Frame(canvas);item=canvas.create_window(0,0,window=content,anchor='nw')
    content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
    def copy(value):
        window.clipboard_clear();window.clipboard_append(value);status.set('선택한 문구를 복사했습니다.')
    def generate():
        if any(a is None for a in selected):
            messagebox.showinfo('계좌 확인','출금·입금 계좌를 확인하세요. 중복 검색은 계좌 선택 버튼을 눌러 선택하세요.',parent=window);return
        value=make_text(prefix.get(),*selected)
        row=ttk.Frame(content,padding=(6,2));row.pack(fill='x',pady=1);lines.append(row)
        ttk.Button(row,text='복사',width=5,style='Compact.TButton',command=lambda:copy(value)).pack(side='right',padx=(10,0))
        label=ttk.Label(row,text=value,wraplength=650);label.pack(side='left',fill='x',expand=True)
        row.bind('<Configure>',lambda e:label.configure(wraplength=max(200,e.width-100)))
        content.update_idletasks();canvas.yview_moveto(1)
        status.set(f'문구 {len(lines)}개 · 각 문구 옆 복사 버튼을 사용하세요.')
    def focus_deposit(event):
        account_entries[1].focus_set()
        return 'break'
    def generate_from_keyboard(event):
        generate()
        return 'break'
    account_entries[0].bind('<Tab>',focus_deposit)
    account_entries[1].bind('<Return>',generate_from_keyboard)
    account_entries[1].bind('<KP_Enter>',generate_from_keyboard)
    def clear_input():
        for q in queries:q.set('')
        prefix.set('자금이체')
    def clear_output():
        for row in lines:row.destroy()
        lines.clear();status.set('화면의 생성 문구를 비웠습니다.')
    ttk.Button(actions,text='문구 생성',command=generate,style='Primary.TButton').pack(side='left')
    ttk.Button(actions,text='입력 비우기',command=clear_input).pack(side='left',padx=8)
    ttk.Button(actions,text='생성 문구 비우기',command=clear_output).pack(side='right')
    window.after(100,load)
