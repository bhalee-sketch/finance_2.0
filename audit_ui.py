"""연도별 원장 파일의 적요 예비 점검."""
from collections import Counter
from pathlib import Path
import qt_ui as tk
from qt_ui import ttk,messagebox
from finance_ui import shell,saved,target_file,compact_combo
from statement_catalog import amount_text
from analysis_runtime import load_audit_sources as load_sources,program_ledger_paths
from audit_review import (AccountOrder,review_values,review_years,select_reviews,
                          export_review,AUDIT_HEADERS,CAPITAL_REVIEW,REVIEW_VIEWS,AUDIT_VISIBLE_HEADERS,visible_review_values,normalized)
from ui_theme import dark_titlebar


class ReviewModel(tk.C.QAbstractTableModel):
    """Keep one reference to the filtered list and format only requested cells."""
    role=tk.C.Qt.ItemDataRole

    def __init__(self,tree):
        super().__init__(tree._q)
        self.tree=tree
        self.items=[]

    def replace(self,items):
        self.beginResetModel()
        self.items=items
        self.endResetModel()

    def rowCount(self,parent=tk.C.QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self,parent=tk.C.QModelIndex()):
        return 0 if parent.isValid() else len(AUDIT_VISIBLE_HEADERS)

    def headerData(self,section,orientation,role=role.DisplayRole):
        if role==self.role.DisplayRole and orientation==tk.C.Qt.Orientation.Horizontal:
            return AUDIT_VISIBLE_HEADERS[section]

    def data(self,index,role=role.DisplayRole):
        if not index.isValid():
            return None
        title=AUDIT_VISIBLE_HEADERS[index.column()]
        item=self.items[index.row()]
        money=title in ('차변','대변')
        if role in (self.role.DisplayRole,self.role.ToolTipRole,self.role.UserRole):
            value=item['reason'] if title=='확인 사유' else item['record'][title]
            return amount_text(value) if money and role!=self.role.UserRole else value
        if role==self.role.TextAlignmentRole:
            return tk.C.Qt.AlignmentFlag.AlignVCenter | (tk.C.Qt.AlignmentFlag.AlignRight if money else tk.C.Qt.AlignmentFlag.AlignLeft)
        if role==self.role.FontRole:
            return self.tree._font(None,money).q
        if item['state'] in ('분류 의심','적요 불충분'):
            if role==self.role.BackgroundRole:
                color='#644C20' if item['state']=='분류 의심' else '#303E55'
                return tk.G.QColor(self.tree._color(color))
            if role==self.role.ForegroundRole:
                return tk.G.QColor(self.tree._color('#FFFFFF'))


def open_audit(parent,desktop,center,open_file):
    window,body,status,jobs=shell(parent,'계정과목 검토',center,show_status=False)
    settings=desktop()/'settings';data=None

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
    list_info=tk.StringVar()
    ttk.Label(review_tab,textvariable=list_info).pack(side='bottom',anchor='w',pady=6)
    tree=ttk.Treeview(review_tab,columns=AUDIT_VISIBLE_HEADERS,show='headings')
    tree.pack(fill='both',expand=True)
    view=tree._q
    model=ReviewModel(tree)
    tree.proxy.setSourceModel(model)
    header=view.horizontalHeader()
    header.setMinimumSectionSize(30)
    header.setSectionResizeMode(tk.W.QHeaderView.ResizeMode.Interactive)
    view.setStyleSheet('QHeaderView::section {padding:2px 3px;} QTableView::item {padding:0;}')
    row_header=view.verticalHeader()
    row_header.setMinimumSectionSize(1)

    preferences=tree._width_preferences
    natural_widths=[0]*len(AUDIT_VISIBLE_HEADERS)
    fitting=False

    def remember_drag(index,_old_width,new_width):
        if not fitting and tk.W.QApplication.mouseButtons() & tk.C.Qt.MouseButton.LeftButton:
            preferences.locked[AUDIT_VISIBLE_HEADERS[index]]=new_width
    header.sectionResized.connect(remember_drag)

    def fit_results(event=None):
        nonlocal fitting
        row_height=max(tree._font(None,numeric).metrics('linespace') for numeric in (True,False))+3
        if row_header.defaultSectionSize()!=row_height:
            row_header.setDefaultSectionSize(row_height)
        if fitting or view.viewport().width()<100:
            return
        minimum=[]
        preferred=[]
        for title,measured in zip(AUDIT_VISIBLE_HEADERS,natural_widths):
            floor=max(header.minimumSectionSize(),header.fontMetrics().horizontalAdvance(title)+14)
            if title in ('전표번호','적요','차변','대변'):
                floor=max(floor,measured)
            minimum.append(preferences.width(title,floor))
            preferred.append(preferences.width(title,max(floor,measured)))
        # Let the table scroll if the voucher, memo and amounts need more room.
        low,high=0,max(preferred)
        while low<high:
            cap=(low+high+1)//2
            total=sum(max(floor,min(width,cap)) for floor,width in zip(minimum,preferred))
            if total<=view.viewport().width():
                low=cap
            else:
                high=cap-1
        fitting=True
        try:
            for i,title in enumerate(AUDIT_VISIBLE_HEADERS):
                width=max(minimum[i],min(preferred[i],low))
                if view.columnWidth(i)!=width:
                    tree.column(title,width=width)
        finally:
            fitting=False

    tree.bind('<Configure>',fit_results,add='+')
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
    measured_blocks=set()
    def measure_visible(*_):
        # Measure nearby rows once per block. Scrolling to the end is immediate
        # even for an entire fiscal year of ledger entries.
        first=max(0,view.rowAt(0))
        last=view.rowAt(view.viewport().height()-1)
        if last<0:
            last=min(model.rowCount()-1,first+max(1,view.viewport().height()//max(1,row_header.defaultSectionSize())+1))
        blocks=set(range(first//64,last//64+1))-measured_blocks
        if not blocks:
            return
        rows=[]
        for block in blocks:
            for i in range(block*64,min((block+1)*64,model.rowCount())):
                index=tree.proxy.mapToSource(tree.proxy.index(i,0))
                rows.append(visible_review_values(model.items[index.row()]))
        measured_blocks.update(blocks)
        for i,title in enumerate(AUDIT_VISIBLE_HEADERS):
            money=title in ('차변','대변')
            metrics=tk.G.QFontMetrics(tree._font(None,money).q)
            values={row[i] for row in rows}
            for value in values:
                label=amount_text(value) if money else str(value or '')
                natural_widths[i]=max(natural_widths[i],metrics.horizontalAdvance(label)+12)
        fit_results()

    def reset_measurements(*_):
        measured_blocks.clear()
        natural_widths[:]=[0]*len(AUDIT_VISIBLE_HEADERS)
        measure_visible()
        fit_results()

    view.verticalScrollBar().valueChanged.connect(measure_visible)
    tree.proxy.layoutChanged.connect(reset_measurements)
    tree.bind('<Configure>',measure_visible,add='+')
    window.bind('<<ThemeChanged>>',reset_measurements,add='+')

    def render():
        if data is None:return
        chosen=current_filters();q=query.get().strip().casefold()
        matched=select_reviews(data,source_year.get(),chosen,q)
        counts=Counter(x['state'] for x in matched)
        mode=review_view.get()
        if mode==CAPITAL_REVIEW:
            selected=[x for x in matched if x['candidate']==CAPITAL_REVIEW]
        else:
            selected=matched if mode=='전체' else [x for x in matched if x['state']==mode]
        info.set(f'원장 파일 연도: {source_year.get() or "없음"} · 조건 일치 {len(matched):,}건 · 분류 의심 {counts["분류 의심"]:,}건 · 적요 불충분 {counts["적요 불충분"]:,}건 · 규칙 미등록 {counts["규칙 미등록"]:,}건')
        model.replace(selected)
        view.scrollToTop()
        reset_measurements()
        list_info.set(f'표시 {len(selected):,}건 · 행을 더블클릭하면 상세 근거를 볼 수 있습니다.')
        status.set(' / '.join(data['issues']) or '과목 순서: 최신 재무제표 기준 · 원장에만 있는 과목은 해당 분류 끝에 표시 · 금액순 정렬 없음')
    def changed(key):options(key);render()
    def year_changed(event=None):
        for var in filters.values():var.set('전체')
        refresh()
    year_box.bind('<<ComboboxSelected>>',year_changed)
    for key,box in boxes.items():box.bind('<<ComboboxSelected>>',lambda e,k=key:changed(k))
    def detail(index):
        row=tree.proxy.mapToSource(index).row()
        item=model.items[row]
        dialog=tk.Toplevel(window);dialog.title('계정과목 검토 · 거래 상세');dark_titlebar(dialog);center(dialog,850,620)
        text=tk.Text(dialog,bg='#192131',fg='#EDF2FA',insertbackground='#EDF2FA',wrap='word',padx=16,pady=16,font=('맑은 고딕',11))
        text.pack(fill='both',expand=True)
        lines=[f'{label}: {value if value!="" else "없음"}' for label,value in zip(AUDIT_HEADERS,review_values(item))
               if value!='' or label=='걸린 표현']
        text.insert('1.0','\n'.join(lines));text.configure(state='disabled')
    view.doubleClicked.connect(detail)
    def refresh():
        nonlocal data
        if jobs.busy:return
        try:available=program_ledger_paths(settings)
        except ValueError as e:messagebox.showerror('원장 확인',str(e),parent=window);return
        if source_year.get() not in available:source_year.set(next(iter(available),''))
        data=None;model.replace([]);list_info.set('');year_box.configure(values=list(available))
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
        snapshot=model.items;snapshot_data=data
        def work():
            from analysis_runtime import statement_folder
            statement_folder()
            return export_review(snapshot_data,snapshot,chosen,path)
        jobs.run(work,lambda p:saved(window,status,open_file,p))
    for title,command in [('새로고침',refresh),('확인 결과 Excel 저장',export)]:
        button=ttk.Button(actions,text=title,command=command);button.pack(side='left',padx=4);jobs.controls.append(button)
    window.after(100,refresh)
    return window
