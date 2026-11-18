"""Rental deposits, normalized rent and contract-date-adjusted revenue outlook."""
from datetime import date
from decimal import Decimal
import qt_ui as tk
from qt_ui import ttk,messagebox
from finance_ui import shell,fill
from responsive_ui import wrapping_row
from statement_ui import table,Jobs
from statement_catalog import amount_text
from analysis_charts import bars
from rental_data import load_rentals,status,forecasts,contract_pdfs,table_rows,HEADERS,rounded_won,grouped_forecasts,update_rental,create_rental,clean

CONTRACT_COLUMN_WIDTHS = (78, 137, 246, 89, 124, 154, 66, 101, 119, 104, 89, 112, 265)


def open_rentals(parent,desktop,center,open_file):
    window,body,message,jobs=shell(parent,'임대사항',center,show_status=False)
    settings=desktop()/'settings';folder=settings/'contract'
    records=[];shown=[];issues=[];projection=[];group_headers=[];group_monthly=[];group_annual=[]
    toolbar=wrapping_row(body);toolbar.pack(fill='x',pady=(0,8))
    centered=tk.C.Qt.AlignmentFlag.AlignVCenter

    def control_group():
        group_frame=ttk.Frame(toolbar)
        layout=tk.W.QHBoxLayout(group_frame._q)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(5)
        group_frame.pack(side='left')
        return group_frame

    def add_controls(group_frame,*widgets):
        for widget in widgets:
            group_frame._q.layout().addWidget(widget._q,0,centered)
            widget._q.show()

    def note(**kwargs):
        label=ttk.Label(body,style='Muted.TLabel',wraplength=1120,**kwargs)
        label._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Preferred)
        return label

    note(textvariable=message).pack(side='bottom',fill='x',pady=(6,3))

    group=tk.StringVar(value='전체');state=tk.StringVar(value='전체');query=tk.StringVar()
    asof=tk.StringVar(value=date.today().isoformat());year=tk.StringVar(value=str(date.today().year))
    for label,var,values in [('구분',group,['전체','대학','제네시스랩']),('계약 상태',state,['전체','유효','예정','만료/퇴거','기간 확인'])]:
        controls=control_group()
        combo=ttk.Combobox(controls,textvariable=var,values=values,width=12,state='readonly')
        add_controls(controls,ttk.Label(controls,text=label),combo)
        combo.bind('<<ComboboxSelected>>',lambda e:render())
    controls=control_group()
    add_controls(controls,ttk.Label(controls,text='기준일'),ttk.Entry(controls,textvariable=asof,width=12))
    controls=control_group()
    add_controls(controls,ttk.Label(controls,text='예상 연도'),
                 ttk.Spinbox(controls,textvariable=year,from_=1900,to=9998,width=6))
    actions=control_group()
    refresh_button=ttk.Button(actions,text='새로고침',command=lambda:refresh())
    new_button=ttk.Button(actions,text='신규 입력',command=lambda:open_form())
    add_controls(actions,ttk.Button(actions,text='적용',command=lambda:render()),refresh_button,new_button)
    jobs.controls.extend((refresh_button,new_button))
    controls=control_group()
    add_controls(controls,ttk.Entry(controls,textvariable=query,width=18))
    row_height=max(child.winfo_reqheight() for child in toolbar.winfo_children())
    for child in toolbar.winfo_children():
        child._q.setMinimumHeight(row_height)
    query.trace_add('write',lambda *_:render())
    summary=wrapping_row(body);summary.pack(fill='x',pady=6)
    values=[]
    for title in ('선택 자료 보증금','유효 계약 보증금','유효 계약 월 환산 수익','선택 연도 예상 수익'):
        card=ttk.LabelFrame(summary,text=title,padding=10);card.pack(side='left')
        value=tk.StringVar(value='—');values.append(value)
        ttk.Label(card,textvariable=value,style='Accent.TLabel',wraplength=195).pack(fill='x',anchor='w')
    note(text='연 임대수익 우선 · 월 환산 = 연액 ÷ 12 · 월별 예상은 계약 유효일수로 안분 · 달력연도 기준\n실제 납부시점·자동 갱신·부가세 가감은 미반영합니다. 보증금은 원자료 기재액이며 반환 여부를 판정하지 않습니다.').pack(fill='x',pady=6)
    notebook=ttk.Notebook(body);notebook.pack(fill='both',expand=True)
    contract_tab=ttk.Frame(notebook);notebook.add(contract_tab,text='계약 및 보증금')
    tree=table(contract_tab,HEADERS,column_preferences=False)
    tree.configure(selectmode='browse',style='Rental.Treeview')
    tree._q.horizontalHeader().setSectionResizeMode(tk.W.QHeaderView.ResizeMode.Fixed)
    ttk.Style(tree).configure('Rental.Treeview',rowheight=30)
    from rental_row_buttons import ContractButtons
    pdf_buttons=ContractButtons(tree,lambda record:view_contract(record))
    forecast_tab=ttk.Frame(notebook);notebook.add(forecast_tab,text='월·연 예상 수익')
    forecast_actions=ttk.Frame(forecast_tab);forecast_actions.pack(fill='x',pady=6)
    ttk.Button(forecast_actions,text='월·연 예상 금액',command=lambda:forecast_popup()).pack(side='left')
    plots=ttk.Frame(forecast_tab);plots.pack(fill='both',expand=True)
    canvas=tk.Canvas(plots,bg='#192131',highlightthickness=0,width=1,height=260)
    annual_canvas=tk.Canvas(plots,bg='#192131',highlightthickness=0,width=1,height=260)
    layout_mode=None
    def layout(event):
        nonlocal layout_mode
        wide=event.width>=1000
        if wide==layout_mode:return
        layout_mode=wide
        canvas.grid_forget();annual_canvas.grid_forget()
        plots.columnconfigure(0,weight=3 if wide else 1,minsize=0)
        plots.columnconfigure(1,weight=1 if wide else 0,minsize=360 if wide else 0)
        plots.rowconfigure(0,weight=1);plots.rowconfigure(1,weight=0 if wide else 1)
        canvas.grid(row=0,column=0,sticky='nsew',padx=(0,8) if wide else 0)
        annual_canvas.grid(row=0 if wide else 1,column=1 if wide else 0,sticky='nsew')
    plots.bind('<Configure>',layout)
    def forecast_popup():
        from analysis_table_popup import amount_popup
        from financial_analysis_ui import display_table
        if not group_annual:return
        excluded=max((r[2] for r in projection),default=0)
        rows=[[r[0],rounded_won(r[1]),rounded_won(r[2]),projection[i][2]] for i,r in enumerate(group_monthly)]
        rows.append(['연 합계',*[rounded_won(v) for v in group_annual[0][1:]],excluded])
        dialog=amount_popup(window,['월','대학 예상 수익(원)','제네시스랩 예상 수익(원)','계산 제외 건수'],rows,display_table,f'{year.get()}년 월·연 예상 임대수익 · 원')
        dialog.title('월·연 예상 금액 · 원')
    def criteria():
        ref=date.fromisoformat(asof.get());yr=int(year.get())
        if not 1900<=yr<=9998:raise ValueError('예상 연도를 확인하세요.')
        return ref,yr
    def sum_label(rows,key):
        missing=sum(r[key] is None for r in rows)
        total=sum((r[key] for r in rows if r[key] is not None),Decimal(0))
        return amount_text(rounded_won(total))+'원'+(f' (미입력 {missing}건 제외)' if missing else '')
    def draw():
        bars(canvas,group_headers,group_monthly,'월 예상 수익',legend_below_title=True,whole_won=True,show_total=True)
        bars(annual_canvas,['연도',*group_headers[1:]],group_annual,'연 예상 수익',legend_below_title=True,
             whole_won=True,show_total=True)
    canvas.bind('<Configure>',lambda e:draw())
    annual_canvas.bind('<Configure>',lambda e:draw())
    def render():
        nonlocal shown,projection,group_headers,group_monthly,group_annual
        try:ref,yr=criteria()
        except ValueError:
            message.set('기준일은 YYYY-MM-DD, 예상 연도는 1900~9998로 입력하세요.');return
        search=query.get().strip().casefold()
        shown=[r for r in records if (group.get()=='전체' or r['group']==group.get()) and (state.get()=='전체' or status(r,ref)==state.get()) and (not search or search in (r['tenant']+' '+r['location']+' '+str(r['number'])).casefold())]
        active=[r for r in shown if status(r,ref)=='유효']
        values[0].set(sum_label(shown,'deposit'));values[1].set(sum_label(active,'deposit'));values[2].set(sum_label(active,'monthly'))
        group_headers,group_monthly,group_annual=grouped_forecasts(shown,yr)
        projection=forecasts(shown,yr);excluded=max((r[2] for r in projection),default=0)
        values[3].set(amount_text(rounded_won(sum((r[1] for r in projection),Decimal(0))))+'원'+(f' ({excluded}건 제외)' if excluded else ''))
        rows=table_rows(shown,ref)
        totals=['확인금액 합계','','','','','','',*[rounded_won(sum((r[k] for r in shown if r[k] is not None),Decimal(0))) for k in ('deposit','monthly','annual')],'','','']
        fill(tree,HEADERS,rows+[totals],(7,8,9))
        for i,width in enumerate(CONTRACT_COLUMN_WIDTHS):
            tree.column(str(i),width=width,stretch=False)
        for name in ('사업자등록번호','상태','납부구분'):
            tree.column(str(HEADERS.index(name)),anchor='center')
        tree.tag_configure('attention',foreground='#E9B875');tree.tag_configure('total',background='#244C70',foreground='#FFFFFF')
        for iid,r in zip(tree.get_children(),shown):
            if r['notes'] or status(r,ref)!='유효':tree.item(iid,tags=('attention',))
        tree.item(tree.get_children()[-1],tags=('total',))
        pdf_buttons.reset(shown)
        draw()
        count=len({(r['group'],r['number']) if r['number'] is not None else (r['source'],r['row']) for r in shown})
        message.set(f'{count}개 계약 / {len(shown)}개 임대내역 · 유효 {len(active)}개 내역 · 확인사항 {sum(bool(r["notes"]) for r in shown)}건'+(' · '+' / '.join(issues) if issues else ''))
    def refresh():
        def done(result):
            nonlocal records,issues
            records,issues=result;render()
        jobs.run(lambda:load_rentals(folder),done)
    def view_contract(record):
        paths=contract_pdfs(settings,record)
        if not paths:
            messagebox.showinfo('계약서 보기','해당 계약번호의 PDF가 없습니다.\n대학: settings/contract/campus\n제네시스랩: settings/contract/genesislab\n예: 1. 임대계약서.pdf 형식으로 저장하세요.',parent=window);return
        if len(paths)==1:
            try:open_file(paths[0])
            except Exception as exc:messagebox.showerror('계약서 열기',str(exc),parent=window)
            return
        dialog=tk.Toplevel(window);dialog.title('열 계약서 선택');center(dialog,620,320)
        box=tk.Listbox(dialog,exportselection=False);box.pack(fill='both',expand=True,padx=12,pady=12)
        for path in paths:box.insert('end',path.name)
        def choose():
            if not box.curselection():return
            try:open_file(paths[box.curselection()[0]]);dialog.destroy()
            except Exception as exc:messagebox.showerror('계약서 열기',str(exc),parent=dialog)
        ttk.Button(dialog,text='선택 PDF 열기',command=choose).pack(pady=8);box.bind('<Double-1>',lambda e:choose())
    def edit_record(event):
        if jobs.busy or tree.identify_region(event.x,event.y)!='cell':return
        iid=tree.identify_row(event.y)
        if not iid or tree.identify_column(event.x)=='#12':return
        index=tree.index(iid)
        if index>=len(shown):return
        open_form(shown[index])
    def open_form(record=None):
        if jobs.busy:return
        creating=record is None
        dialog=tk.Toplevel(window);dialog.title('임대사항 신규 입력' if creating else '임대사항 수정');center(dialog,650,740);dialog.transient(window);dialog.grab_set()
        frame=ttk.Frame(dialog,padding=15);frame.pack(fill='both',expand=True)
        new_group=tk.StringVar(value=group.get() if group.get() in ('대학','제네시스랩') else '대학')
        number=tk.StringVar()
        if creating:
            header=ttk.Frame(frame);header.grid(row=0,column=0,columnspan=2,sticky='ew',pady=8)
            ttk.Label(header,text='구분').pack(side='left')
            ttk.Combobox(header,textvariable=new_group,values=['대학','제네시스랩'],state='readonly',width=12).pack(side='left',padx=6)
            ttk.Label(header,text='계약번호 (빈칸: 자동)').pack(side='left',padx=6)
            ttk.Entry(header,textvariable=number,width=8).pack(side='left')
        else:
            ttk.Label(frame,text=f'{record["group"]} · {record["tenant"]}',style='Section.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=8)
        fields=[('building','동'),('floor','층'),('room','호'),('tenant','업체명'),('representative','대표자명'),('business','사업자등록번호'),
                ('period','임대기간'),('entered','입주일'),('renewed','갱신일'),('exited','퇴거일'),('deposit','임대보증금'),('rent','원자료 임대료'),('annual','연 임대수익'),('term','납부구분'),('special','특이사항 (Q열)')]
        inputs={};initial={}
        for rn,(key,label) in enumerate(fields,1):
            value=None if creating else record['raw_values'][key]
            if hasattr(value,'strftime'):value=value.strftime('%Y-%m-%d')
            initial[key]=clean(value);variable=tk.StringVar(value=initial[key]);inputs[key]=variable
            ttk.Label(frame,text=label).grid(row=rn,column=0,sticky='w',padx=(0,12),pady=3)
            ttk.Entry(frame,textvariable=variable).grid(row=rn,column=1,sticky='ew',pady=3)
        frame.columnconfigure(1,weight=1)
        ttk.Label(frame,text='업체명·임대기간은 필수입니다. 월 환산액·상태는 자동 계산합니다. 날짜: YYYY-MM-DD\n원자료 임대료는 납부 단위 금액입니다. 연 수익 수식이 있으면 함께 갱신합니다.\n저장하면 원자료에 반영하며, 이전 파일은 contract/backups에 보관합니다.',wraplength=600).grid(row=16,column=0,columnspan=2,sticky='w',pady=10)
        edit_message=tk.StringVar();edit_jobs=Jobs(dialog,edit_message)
        ttk.Label(frame,textvariable=edit_message,wraplength=600).grid(row=17,column=0,columnspan=2,sticky='w')
        def save():
            changes={key:var.get() for key,var in inputs.items() if creating or var.get()!=initial[key]}
            if not changes:dialog.destroy();return
            destination_group=new_group.get();requested_number=number.get()
            def done(result):
                dialog.destroy()
                if creating:
                    group.set(destination_group);state.set('전체');query.set('')
                    messagebox.showinfo('신규 입력 완료',f'{destination_group} {result["number"]}번 계약을 저장했습니다.\n{result["path"]}',parent=window)
                refresh()
            edit_jobs.run(lambda:create_rental(folder,destination_group,changes,requested_number) if creating else update_rental(record,changes),done)
        button=ttk.Button(frame,text='신규 계약 저장' if creating else '원자료에 저장',command=save);button.grid(row=18,column=1,sticky='e',pady=10);edit_jobs.controls.append(button)
        dialog.protocol('WM_DELETE_WINDOW',lambda:None if edit_jobs.busy else dialog.destroy())
    tree.bind('<Double-1>',edit_record)
    window.after(100,refresh)
