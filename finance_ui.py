"""재무 분석, 보조원장 조회 및 Excel 통합 창."""
from pathlib import Path
from numeric_tree import NumericTreeview
import qt_ui as tk
from qt_ui import ttk, filedialog, messagebox
from decimal import Decimal
from datetime import datetime
from statement_ui import Jobs, table
from statement_catalog import amount_text, discover_years
from finance_data import (LEDGER_COLUMNS, load_ledger, filter_ledger, ledger_summary,
                          export_ledger, merge_excel)
from ui_theme import dark_titlebar

FILETYPES=[('Excel','*.xls *.xlsx *.xlsm')]


def shell(parent,title,center,show_status=True):
    window=tk.Toplevel(parent);window.title(title);dark_titlebar(window)
    center(window,1180,min(800,window.winfo_screenheight()-90))
    body=ttk.Frame(window,padding=12);body.pack(fill='both',expand=True)
    status=tk.StringVar(value='자료를 선택하세요.');jobs=Jobs(window,status)
    if show_status:ttk.Label(body,textvariable=status,style='Muted.TLabel',wraplength=1100).pack(side='bottom',fill='x',pady=(8,0))
    return window,body,status,jobs


def saved(window,status,open_file,path):
    status.set(f'저장 완료: {path}')
    try:open_file(path)
    except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{path}\n{e}',parent=window)


def target_file(window,folder,name):
    # 기존 호출 인터페이스 유지, 저장 위치 선택 없이 공통 결과 폴더 사용.
    from result_paths import result_path
    return result_path(name.removesuffix('.xlsx'))


def fill(tree,headers,rows,numeric=()):
    tree.delete(*tree.get_children());columns=[str(i) for i in range(len(headers))];tree.configure(columns=columns)
    for i,h in enumerate(headers):
        tree.heading(str(i),text=h);tree.column(str(i),width=290 if i==0 else 155,minwidth=70,anchor='e' if i in numeric else 'w')
    for row in rows:tree.insert('','end',values=[amount_text(v) if isinstance(v,(int,float,Decimal)) else ('—' if v is None else v) for v in row])


def content_widths(tree,headers,rows):
    """표 제목과 현재 조회 결과 전체의 표시 문자열을 픽셀로 측정한다."""
    from qt_ui import font as tkfont
    font=tkfont.Font(font=ttk.Style(tree).lookup('Treeview','font') or ('맑은 고딕',10))
    bold=tkfont.Font(font=font);bold.configure(weight='bold')
    from appearance import controller
    from numeric_tree import numeric_cell
    appearance=controller(tree)
    number=tkfont.Font(font=font);number_bold=tkfont.Font(font=bold)
    if appearance:
        number.configure(family=appearance.numeric_family or appearance.family)
        number_bold.configure(family=appearance.numeric_family or appearance.family)
    cache={}
    def measure(value,heading=''):
        value=amount_text(value) if isinstance(value,(int,float,Decimal)) else str(value if value is not None else '—')
        numeric=numeric_cell(heading,value);key=(value,numeric)
        pair=(number,number_bold) if numeric else (font,bold)
        if key not in cache:cache[key]=max(f.measure(value) for f in pair)
        return cache[key]
    widths=[max(45,measure(h)+24) for h in headers]
    for row in rows:
        for i,value in enumerate(row):widths[i]=max(widths[i],measure(value,headers[i])+24)
    return widths


def apply_widths(tree,widths):
    for i,width in enumerate(widths):tree.column(str(i),width=width,minwidth=width,stretch=False)


def compact_combo(box,values):
    """필요한 텍스트 폭만 확보하고 부모 폭에 맞춰 늘리지 않는다."""
    import math
    from qt_ui import font as tkfont
    font=tkfont.Font(font=ttk.Style(box).lookup('TCombobox','font') or ('맑은 고딕',10))
    pixels=max((font.measure(str(v)) for v in values),default=font.measure('전체'))
    box.configure(values=values,width=max(4,math.ceil(pixels/max(1,font.measure('0')))+1))


def open_merge(parent,desktop,center,open_file,ledger=False):
    title='원장통합' if ledger else '재무제표 Excel 통합'
    window,body,status,jobs=shell(parent,title,center);sources=[]
    ttk.Label(body,text='동일한 첫 행 헤더 아래 모든 파일의 데이터를 한 시트에 연결합니다.' if ledger else
              '각 파일의 첫 번째 시트를 파일명으로 된 별도 시트에 통합합니다.',style='Section.TLabel').pack(anchor='w',pady=8)
    ttk.Label(body,text='원본은 변경하지 않습니다. XLS · XLSX · XLSM 지원 · 수식은 저장된 계산값을 가져옵니다.',style='Muted.TLabel').pack(anchor='w')
    bar=ttk.Frame(body);bar.pack(fill='x',pady=12)
    tree=table(body,['파일','위치'])
    from check_list import tree_checks
    checked_files=tree_checks(tree,default=True)
    def render():
        old={i:Path(tree.item(i,'values')[1])/tree.item(i,'values')[0] for i in tree.get_children()}
        checked={old[i] for i in checked_files()}
        tree.delete(*tree.get_children())
        for i,p in enumerate(sources):
            iid=tree.insert('','end',iid=str(i),values=[p.name,str(p.parent)])
            checked_files.set_checked(iid,p not in old.values() or p in checked)
        status.set(f'{len(sources)}개 파일 · 선택 순서대로 통합' if ledger else f'{len(sources)}개 파일 · 회계단위 / 재무제표 구분 순으로 통합')
    def add():
        names=filedialog.askopenfilenames(parent=window,initialdir=str(desktop()/'settings'),filetypes=FILETYPES)
        add_paths(names)
    def add_paths(names):
        if jobs.busy:return
        from file_drop import excel_paths
        valid,rejected=excel_paths(names,sources)
        sources.extend(valid)
        render()
        if rejected:messagebox.showwarning('파일 확인','Excel 파일(.xls/.xlsx/.xlsm)만 추가할 수 있습니다.\n'+'\n'.join(rejected),parent=window)
    if ledger:
        drop=ttk.Label(bar,text='Excel 파일을 이 창으로 끌어 놓으세요.',style='Accent.TLabel');drop.pack(side='right',padx=10)
        def dropped(event):
            if jobs.busy:return 'none'
            try:add_paths(window.tk.splitlist(event.data))
            except (tk.TclError,ValueError) as e:messagebox.showerror('파일 추가',str(e),parent=window)
            return 'copy'
        try:
            DND_FILES='DND_Files'
            for widget in (window,tree,drop):
                widget.drop_target_register(DND_FILES);widget.dnd_bind('<<Drop>>',dropped)
        except (ImportError,AttributeError,tk.TclError):
            drop.configure(text='파일 추가 사용 · 드래그 지원은 최신 실행 파일로 재실행하세요.')
    def remove():
        for i in sorted([int(i) for i in checked_files()],reverse=True):sources.pop(i)
        render()
    def execute():
        if not sources:messagebox.showinfo(title,'통합할 파일을 추가하세요.',parent=window);return
        target=target_file(window,sources[0].parent,'원장통합' if ledger else '재무제표 Excel 통합')
        if not target:return
        selected=[sources[int(i)] for i in checked_files()]
        if not selected:messagebox.showinfo(title,'통합할 파일에 체크하세요.',parent=window);return
        def done(result):
            saved(window,status,open_file,result[0]);status.set(f'{len(selected)}개 파일 · 데이터 {result[1]:,}행 통합 완료: {result[0]}')
        jobs.run(lambda:merge_excel(selected,target,ledger),done)
    for label,command in [('파일 추가',add),('체크 파일 제거',remove),('통합 · 저장',execute)]:
        button=ttk.Button(bar,text=label,command=command);button.pack(side='left',padx=(0,8));jobs.controls.append(button)
    tree.column('파일',width=380);tree.column('위치',width=650)


def open_ledger(parent,desktop,center,open_file):
    from ledger_layout import COMPACT_COLUMNS,fit_ledger_columns
    from finance_data import (BUSINESS_COLUMNS,LEDGER_DISPLAY_COLUMNS,discover_ledger_years,
                              ledger_total_row,ledger_totals)
    window,body,status,jobs=shell(parent,'보조원장 조회',center)
    from audit_review import AccountOrder,load_statement_history,matches
    records=[];selected=[];source=None;page=0;page_size=300;paths={};order=AccountOrder();order_notes=[]
    folder=desktop()/'settings'/'lodges';source_year=tk.StringVar()
    top=ttk.Frame(body);top.pack(fill='x',pady=(0,8))
    ttk.Label(top,text='원장 연도',style='Accent.TLabel').pack(side='left',padx=(0,6))
    year_box=ttk.Combobox(top,textvariable=source_year,state='readonly',width=9)
    year_box.pack(side='left',padx=(0,10));jobs.controls.append(year_box)
    label=tk.StringVar(value='settings/lodges의 연도별 원장을 확인합니다.')
    ttk.Label(top,textvariable=label,style='Muted.TLabel').pack(side='left')
    filters={};boxes={};filterbar=ttk.Frame(body);filterbar.pack(fill='x')
    fields=['회계단위','관','항','목'];businessbar=filterbar
    for names,parent_bar in ((fields,filterbar),(BUSINESS_COLUMNS,businessbar)):
        for name in names:
            cell=ttk.Frame(parent_bar);cell.pack(side='left',padx=(0,8))
            ttk.Label(cell,text=name).pack(anchor='w')
            var=tk.StringVar(value='전체');filters[name]=var
            box=ttk.Combobox(cell,textvariable=var,state='readonly',width=5)
            box.pack(fill='x');boxes[name]=box;jobs.controls.append(box)
    querybar=ttk.Frame(body);querybar.pack(fill='x',pady=8)
    start=tk.StringVar();end=tk.StringVar();query=tk.StringVar()
    for text,var,width in [('시작일',start,12),('종료일',end,12),('거래선·적요 등',query,27)]:
        ttk.Label(querybar,text=text).pack(side='left',padx=(0,4))
        entry=ttk.Entry(querybar,textvariable=var,width=width);entry.pack(side='left',padx=(0,10));jobs.controls.append(entry)
        entry.bind('<Return>',lambda e:apply())
    show_all=tk.BooleanVar(value=False)
    ttk.Checkbutton(querybar,text='전체 열 표시',variable=show_all,command=lambda:show_page()).pack(side='right')
    ttk.Label(body,text='기본: 주요 8개 열 · 긴 내용은 거래를 더블클릭하여 확인 · 날짜: YYYY-MM-DD',style='Muted.TLabel').pack(anchor='w',pady=(0,6))
    totals=tk.StringVar();ttk.Label(body,textvariable=totals,style='Accent.TLabel').pack(fill='x',pady=(0,6))
    detail_tab=ttk.Frame(body);detail_tab.pack(fill='both',expand=True)
    pager=ttk.Frame(detail_tab);pager.pack(side='bottom',fill='x',pady=6)
    page_label=tk.StringVar();ttk.Label(pager,textvariable=page_label).pack(side='left')
    # 합계는 페이지와 무관하게 표 아래에 고정하고 본문과 가로 스크롤을 맞춘다.
    sum_frame=ttk.Frame(detail_tab);sum_frame.pack(side='bottom',fill='x')
    total_tree=NumericTreeview(sum_frame,show='',height=1,selectmode='none');total_tree.pack(side='left',fill='x',expand=True)
    total_tree.tag_configure('total',background='#244C70',foreground='#FFFFFF',font=('맑은 고딕',10,'bold'))
    columns=LEDGER_DISPLAY_COLUMNS;detail=table(detail_tab,columns)
    scrollbar_size=next((child.winfo_reqwidth() for child in detail.master.winfo_children()
                         if isinstance(child,ttk.Scrollbar) and str(child.cget('orient'))=='vertical'),14)
    ttk.Frame(sum_frame,width=int(scrollbar_size)).pack(side='right',fill='y')
    original_scroll=detail.cget('xscrollcommand')
    horizontal=next(child for child in detail.master.winfo_children() if isinstance(child,ttk.Scrollbar) and str(child.cget('orient'))=='horizontal')
    def scroll_changed(first,last):
        original_scroll(first,last) if callable(original_scroll) else None;total_tree.xview_moveto(float(first))
        if float(first)<=0 and float(last)>=1:horizontal.grid_remove()
        else:horizontal.grid()
    detail.configure(xscrollcommand=scroll_changed)
    measurements={};detail_widths=[]
    def widths(headers,data):return content_widths(detail,headers,data)
    def fit(tree,base,footer=None):
        if not base:return
        names=columns if show_all.get() else COMPACT_COLUMNS
        indices=[columns.index(name) for name in names]
        displayed=[str(i) for i in indices]
        tree.configure(displaycolumns=displayed)
        if footer is not None:footer.configure(displaycolumns=displayed)
        fitted=fit_ledger_columns(names,[base[i] for i in indices],tree.winfo_width()-4)
        for index,width in zip(indices,fitted):
            tree.column(str(index),width=width,minwidth=width,stretch=False)
            if footer is not None:footer.column(str(index),width=width,minwidth=width,stretch=False)
        if footer is not None:footer.xview_moveto(detail.xview()[0])
    detail.bind('<Configure>',lambda e:fit(detail,detail_widths,total_tree),add='+')
    detail.bind('<ButtonRelease-1>',lambda e:fit(detail,detail_widths,total_tree),add='+')
    def show_page():
        visible=selected[page*page_size:(page+1)*page_size]
        numeric=[columns.index(c) for c in ('차변','대변')]
        fill(detail,columns,[[r[c] for c in columns] for r in visible],numeric=numeric)
        total_values=ledger_total_row(selected,columns)
        if not show_all.get():
            total_values[0]='';total_values[columns.index(COMPACT_COLUMNS[0])]='전체 합계'
        fill(total_tree,columns,[total_values],numeric=numeric)
        for item in total_tree.get_children():total_tree.item(item,tags=('total',))
        fit(detail,detail_widths,total_tree)
        page_label.set(f'{page+1} / {max(1,(len(selected)+page_size-1)//page_size)}쪽 · 전체 {len(selected):,}건 · 아래 합계와 Excel은 조회 전체 기준')
    def open_transaction(event=None):
        ids=detail.selection()
        if not ids:return
        record=selected[page*page_size+detail.index(ids[0])]
        dialog=tk.Toplevel(window);dialog.title('보조원장 · 거래 상세');dark_titlebar(dialog)
        center(dialog,min(820,dialog.winfo_screenwidth()-60),min(650,dialog.winfo_screenheight()-90))
        text=tk.Text(dialog,wrap='word',bg='#192131',fg='#EDF2FA',insertbackground='#EDF2FA',font=('맑은 고딕',11),padx=18,pady=14)
        scroll=ttk.Scrollbar(dialog,command=text.yview);text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0','\n\n'.join(f'{name}  :  {amount_text(record[name]) if name in ("차변","대변") else record[name]}' for name in LEDGER_COLUMNS))
        text.configure(state='disabled')
    detail.bind('<Double-1>',open_transaction)
    def move(delta):
        nonlocal page
        page=max(0,min(max(0,(len(selected)-1)//page_size),page+delta));show_page()
    ttk.Button(pager,text='이전',command=lambda:move(-1)).pack(side='right',padx=4)
    ttk.Button(pager,text='다음',command=lambda:move(1)).pack(side='right',padx=4)
    def chosen(k):return '' if filters[k].get()=='전체' else filters[k].get()
    def options(changed=None):
        if changed=='회계단위':
            for k in ['관','항','목']+BUSINESS_COLUMNS:filters[k].set('전체')
        elif changed in ('관','항','목'):
            for k in fields[fields.index(changed)+1:]+BUSINESS_COLUMNS:filters[k].set('전체')
        elif changed in BUSINESS_COLUMNS:
            for k in BUSINESS_COLUMNS[BUSINESS_COLUMNS.index(changed)+1:]:filters[k].set('전체')
        for i,k in enumerate(fields+BUSINESS_COLUMNS):
            dependencies=(fields+BUSINESS_COLUMNS)[:i]
            subset=[r for r in records if matches(r,{p:chosen(p) for p in dependencies})]
            choices=['전체']+(order.choices(subset,k) if k in ('관','항','목') else list(dict.fromkeys(r[k] for r in subset if r[k] and r[k]!='전체')))
            compact_combo(boxes[k],choices)
            if filters[k].get() not in choices:filters[k].set('전체')
    def apply():
        nonlocal selected,page,detail_widths
        if jobs.busy:return
        try:result=filter_ledger([r for r in records if matches(r,{k:chosen(k) for k in filters})],{},start.get(),end.get(),query.get())
        except ValueError as e:messagebox.showerror('조회 조건',str(e),parent=window);return
        selected=sorted(result,key=order.key);page=0
        # 필터 결과 전체로 너비를 계산하므로 페이지를 넘겨도 열 폭이 흔들리지 않는다.
        detail_widths=widths(columns,([r[c] for c in columns] for r in selected))
        total_values=ledger_total_row(selected,columns)
        detail_widths=[max(a,b) for a,b in zip(detail_widths,widths(columns,[total_values]))]
        amount=ledger_totals(selected);debit=amount['차변'];credit=amount['대변']
        totals.set(f'{len(selected):,}건  |  차변 {amount_text(debit)}원  |  대변 {amount_text(credit)}원  |  차변-대변 {amount_text(debit-credit)}원')
        show_page();status.set('조회 완료 · 차변-대변은 거래 순액입니다. '+(' / '.join(order_notes) if order_notes else '과목은 재무제표 순서로 표시합니다.'))
    def changed(k):options(k);apply()
    for k,box in boxes.items():box.bind('<<ComboboxSelected>>',lambda e,key=k:changed(key))
    def clear_data():
        nonlocal records,selected,source
        records=[];selected=[];source=None;measurements.clear()
        for v in filters.values():v.set('전체')
        start.set('');end.set('');query.set('');options();apply()
    def load_year(event=None):
        if jobs.busy:return
        path=paths.get(source_year.get());clear_data()
        if path is None:return
        label.set(path.name)
        def done(result):
            nonlocal records,source,order,order_notes
            records,history,order_notes=result;order=AccountOrder(history,records);source=path;options();apply()
        def work():
            rows=load_ledger(path)
            try:history,notes,_=load_statement_history(desktop()/'settings')
            except Exception as e:history={};notes=[f'재무제표 순서 확인 필요: {e}']
            return rows,history,notes
        jobs.run(work,done)
    def refresh():
        nonlocal paths
        if jobs.busy:return
        clear_data();paths={};year_box.configure(values=[])
        try:paths=discover_ledger_years(folder)
        except ValueError as e:
            source_year.set('');label.set('원장 파일 확인 필요');status.set(str(e));messagebox.showerror('원장 연도',str(e),parent=window);return
        year_box.configure(values=list(paths))
        if not paths:
            source_year.set('');label.set('원장 파일 없음');status.set(f'{folder}에 2026.xls 또는 2026회계연도.xlsx처럼 저장하세요.');return
        if source_year.get() not in paths:source_year.set(next(iter(paths)))
        load_year()
    year_box.bind('<<ComboboxSelected>>',load_year)
    def reset():
        for v in filters.values():v.set('전체')
        start.set('');end.set('');query.set('');options();apply()
    def export():
        if source is None:return
        target=target_file(window,None,'보조원장 조회')
        if not target:return
        if Path(target).resolve() in {p.resolve() for p in paths.values()}:
            messagebox.showerror('저장 위치','원본과 다른 파일명으로 저장하세요.',parent=window);return
        data=list(selected)
        jobs.run(lambda:export_ledger(data,target,include_summary=False),lambda p:saved(window,status,open_file,p))
    for text,command in [('Excel 저장',export),('조건 초기화',reset),('조회',apply),('연도 새로고침',refresh)]:
        button=ttk.Button(top,text=text,command=command);button.pack(side='right',padx=4);jobs.controls.append(button)
    window.after(100,refresh)


def open_analysis(parent,desktop,center,open_file):
    from financial_analysis_ui import open_financial_analysis
    return open_financial_analysis(parent,desktop,center,open_file)
