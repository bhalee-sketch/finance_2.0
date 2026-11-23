"""연도별 원장 파일의 적요 예비 점검."""
from collections import Counter
from pathlib import Path
import qt_ui as tk
from qt_ui import ttk,messagebox
from finance_ui import shell,saved,target_file,compact_combo
from statement_ui import table
from statement_catalog import amount_text
from analysis_runtime import load_audit_sources as load_sources,program_ledger_paths
from audit_review import (AccountOrder,review_values,review_years,select_reviews,
                          export_review,AUDIT_HEADERS,REVIEW_VIEWS,AUDIT_VISIBLE_HEADERS,visible_review_values,normalized)
from ui_theme import dark_titlebar


def open_audit(parent,desktop,center,open_file):
    window,body,status,jobs=shell(parent,'계정과목 검토',center,show_status=False)
    settings=desktop()/'settings';data=None;selected=[];page=0;page_size=200

    def wrapped_label(**kwargs):
        label=ttk.Label(body,wraplength=1100,**kwargs)
        label._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Preferred)
        return label

    wrapped_label(textvariable=status,style='Muted.TLabel').pack(side='bottom',fill='x',pady=(6,3))
    source_year=tk.StringVar()
    bar=ttk.Frame(body);bar.pack(fill='x',pady=(0,8));filters={};boxes={}
    year_group=ttk.Frame(bar);year_group.pack(side='left',padx=(0,10))
    ttk.Label(year_group,text='원장 연도').pack(anchor='w')
    year_box=ttk.Combobox(year_group,textvariable=source_year,state='readonly',width=8);year_box.pack();jobs.controls.append(year_box)
    for key in ('회계단위','관','항','목'):
        group=ttk.Frame(bar);group.pack(side='left',padx=(0,10))
        ttk.Label(group,text=key).pack(anchor='w')
        var=tk.StringVar(value='전체');filters[key]=var
        box=ttk.Combobox(group,textvariable=var,state='readonly',width=5);box.pack()
        boxes[key]=box;jobs.controls.append(box)
    actions=ttk.Frame(bar);actions.pack(side='right',anchor='n')
    controls=ttk.Frame(body);controls.pack(fill='x',pady=(0,8))
    review_view=tk.StringVar(value=REVIEW_VIEWS[0]);query=tk.StringVar()
    ttk.Label(controls,text='표시 대상').pack(side='left',padx=(0,6))
    selector=ttk.Combobox(controls,textvariable=review_view,values=REVIEW_VIEWS,state='readonly',width=12)
    selector.pack(side='left');jobs.controls.append(selector)
    selector.bind('<<ComboboxSelected>>',lambda e:render())
    ttk.Label(controls,text='적요·거래선·전표 검색').pack(side='left',padx=(14,6))
    search=ttk.Entry(controls,textvariable=query,width=30);search.pack(side='left');search.bind('<Return>',lambda e:render());jobs.controls.append(search)
    button=ttk.Button(controls,text='검색',command=lambda:render());button.pack(side='left',padx=6);jobs.controls.append(button)
    info=tk.StringVar(value='연도별 원장과 재무제표를 자동으로 불러옵니다.')
    wrapped_label(textvariable=info,style='Accent.TLabel').pack(fill='x',pady=(0,5))
    wrapped_label(text='2023.12 해설서 기반의 제한적 적요 점검입니다. 탐지 사항 없음은 적정 판정이 아니며, 규칙 미등록 과목은 미점검입니다.',style='Muted.TLabel').pack(fill='x',pady=(0,7))
    review_tab=ttk.Frame(body);review_tab.pack(fill='both',expand=True)
    pager=ttk.Frame(review_tab);pager.pack(side='bottom',fill='x',pady=6);page_text=tk.StringVar()
    ttk.Label(pager,textvariable=page_text).pack(side='left')
    tree=table(review_tab,AUDIT_VISIBLE_HEADERS,column_preferences=True)
    view=tree._q
    header=view.horizontalHeader()
    header.setMinimumSectionSize(30)
    header.setSectionResizeMode(tk.W.QHeaderView.ResizeMode.Interactive)
    view.setStyleSheet('QHeaderView::section {padding:2px 3px;} QTableView::item {padding:0;}')
    row_header=view.verticalHeader()
    row_header.setMinimumSectionSize(1)

    for title in ('차변','대변'):
        tree.column(title,anchor='e')

    user_sized=False
    def remember_drag(*_):
        nonlocal user_sized
        if tk.W.QApplication.mouseButtons() & tk.C.Qt.MouseButton.LeftButton:
            user_sized=True
    header.sectionResized.connect(remember_drag)

    def fit_results(event=None):
        row_height=max(tree._font(None,numeric).metrics('linespace') for numeric in (True,False))+3
        if row_header.defaultSectionSize()!=row_height:
            row_header.setDefaultSectionSize(row_height)
        if user_sized or not view.isVisible() or view.viewport().width() < 100:
            return
        metrics=header.fontMetrics()
        weights=(16,6,10,10,28,14,14,26,26,22,70,36,48,40,18)
        widths=[max(30,metrics.horizontalAdvance(title)+16) for title in AUDIT_VISIBLE_HEADERS]
        space=view.viewport().width()-sum(widths)
        if space < 0:
            weights=[width-header.minimumSectionSize() for width in widths]
            widths=[header.minimumSectionSize()]*len(widths)
            space=max(0,view.viewport().width()-sum(widths))
        total_weight=max(1,sum(weights))
        for index,(title,width,weight) in enumerate(zip(AUDIT_VISIBLE_HEADERS,widths,weights)):
            wanted=width+space*weight//total_weight
            if view.columnWidth(index)!=wanted:
                tree.column(title,width=wanted)

    tree.bind('<Configure>',fit_results,add='+')
    tree.tag_configure('suspect',background='#644C20',foreground='#FFFFFF')
    tree.tag_configure('info',background='#303E55',foreground='#FFFFFF')
    def current_filters():return {k:v.get() for k,v in filters.items()}
    def options(changed=None):
        keys=list(filters)
        if changed:
            for key in keys[keys.index(changed)+1:]:filters[key].set('전체')
        records=[x['record'] for x in select_reviews(data,source_year.get(),{})] if data else []
        order=data['order'] if data else AccountOrder()
        candidates=records
        for index,key in enumerate(keys):
            if key=='회계단위':choices=['전체']+list(dict.fromkeys(r['회계단위'] for r in candidates if r['회계단위'] not in ('','전체')))
            elif key in ('항','목') and filters[keys[index-1]].get()=='전체':choices=['전체']
            else:
                choices=['전체']+order.choices(candidates,key)
            if filters[key].get() not in choices:filters[key].set('전체')
            compact_combo(boxes[key],choices)
            value=filters[key].get()
            if index+1<len(keys) and value and value!='전체':
                target=normalized(value)
                candidates=[record for record in candidates if normalized(record.get(key,''))==target]
    def show_page():
        visible=selected[page*page_size:(page+1)*page_size]
        fit_results()
        tree.delete(*tree.get_children())
        for result in visible:
            values=visible_review_values(result)
            for column in ('차변','대변'):
                index=AUDIT_VISIBLE_HEADERS.index(column)
                values[index]=amount_text(values[index])
            tag={'분류 의심':'suspect','적요 불충분':'info'}.get(result['state'])
            tree.insert('','end',values=values,tags=(tag,) if tag else ())
        page_text.set(f'{page+1}/{max(1,(len(selected)+page_size-1)//page_size)}쪽 · 표시 {len(selected):,}건 · 더블클릭: 상세 근거 · Excel: 표시 조건 전체')
    def move(delta):
        nonlocal page
        page=max(0,min(max(0,(len(selected)-1)//page_size),page+delta));show_page()
    for title,delta in [('다음',1),('이전',-1)]:ttk.Button(pager,text=title,command=lambda d=delta:move(d)).pack(side='right',padx=4)
    def render():
        nonlocal selected,page
        if data is None:return
        chosen=current_filters();q=query.get().strip().casefold()
        matched=select_reviews(data,source_year.get(),chosen,q)
        counts=Counter(x['state'] for x in matched)
        mode=review_view.get()
        selected=matched if mode=='전체' else [x for x in matched if x['state']==mode]
        page=0
        info.set(f'원장 파일 연도: {source_year.get() or "없음"} · 조건 일치 {len(matched):,}건 · 분류 의심 {counts["분류 의심"]:,}건 · 적요 불충분 {counts["적요 불충분"]:,}건 · 규칙 미등록 {counts["규칙 미등록"]:,}건')
        show_page()
        status.set(' / '.join(data['issues']) or '과목 순서: 최신 재무제표 기준 · 원장에만 있는 과목은 해당 분류 끝에 표시 · 금액순 정렬 없음')
    def changed(key):options(key);render()
    def year_changed(event=None):
        for var in filters.values():var.set('전체')
        refresh()
    year_box.bind('<<ComboboxSelected>>',year_changed)
    for key,box in boxes.items():box.bind('<<ComboboxSelected>>',lambda e,k=key:changed(k))
    def detail(event=None):
        ids=tree.selection()
        if not ids:return
        index=page*page_size+tree.index(ids[0]);item=selected[index]
        dialog=tk.Toplevel(window);dialog.title('계정과목 검토 · 거래 상세');dark_titlebar(dialog);center(dialog,850,620)
        text=tk.Text(dialog,bg='#192131',fg='#EDF2FA',insertbackground='#EDF2FA',wrap='word',padx=16,pady=16,font=('맑은 고딕',11))
        scrollbar=ttk.Scrollbar(dialog,command=text.yview);text.configure(yscrollcommand=scrollbar.set);scrollbar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        lines=[f'{label}: {value}' for label,value in zip(AUDIT_HEADERS,review_values(item)) if value!='']
        text.insert('1.0','\n'.join(lines));text.configure(state='disabled')
    tree.bind('<Double-1>',detail)
    def refresh():
        nonlocal data,selected
        if jobs.busy:return
        try:available=program_ledger_paths(settings)
        except ValueError as e:messagebox.showerror('원장 확인',str(e),parent=window);return
        if source_year.get() not in available:source_year.set(next(iter(available),''))
        data=None;selected=[];tree.delete(*tree.get_children());year_box.configure(values=list(available))
        def done(result):
            nonlocal data
            data=result;years=review_years(data);year_box.configure(values=years)
            if source_year.get() not in years:source_year.set(years[0] if years else '')
            options();render()
        requested_year=source_year.get()
        jobs.run(lambda:load_sources(settings,requested_year),done)
    def export():
        if data is None:return
        path=target_file(window,None,'계정과목 검토')
        if not path:return
        if Path(path).resolve() in {Path(p).resolve() for p in data['sources']}:
            messagebox.showerror('저장 위치','원본과 다른 이름으로 저장하세요.',parent=window);return
        chosen=current_filters()|{'원장 연도':source_year.get(),'표시':review_view.get(),'검색':query.get()}
        snapshot=list(selected);snapshot_data=data
        def work():
            from analysis_runtime import statement_folder
            statement_folder()
            return export_review(snapshot_data,snapshot,chosen,path)
        jobs.run(work,lambda p:saved(window,status,open_file,p))
    for title,command in [('새로고침',refresh),('확인 결과 Excel 저장',export)]:
        button=ttk.Button(actions,text=title,command=command);button.pack(side='left',padx=4);jobs.controls.append(button)
    window.after(100,refresh)
    return window
