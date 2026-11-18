"""9~11번: 재무제표 조회/저장, 합산 비교, 부속명세서 비교."""
from datetime import datetime
from pathlib import Path
import queue
import threading
import qt_ui as tk
from qt_ui import font as tkfont
from qt_ui import ttk,filedialog,messagebox
from openpyxl import Workbook
from openpyxl.styles import Font,PatternFill,Alignment
from ui_theme import dark_titlebar


def output_path(source,label):
    from result_paths import result_path
    return result_path(label)


def export_appendix(result,path):
    w=Workbook();s=w.active;s.title='부속명세서 검증'
    s.append(['구분','계정과목','재무제표','부속명세서','차이','결과','부속 시트'])
    for item in result['items']:
        missing=item['fs_amount'] is None or item['supp_amount'] is None
        s.append([item['category'],item['account'],item['fs_amount'],item['supp_amount'],
                  None if missing else item['diff'],'일치' if item['is_match'] else '확인필요',item['supp_sheet']])
        if not item['is_match']:
            for c in s[s.max_row]:c.fill=PatternFill('solid',fgColor='FDE8E8')
    for c in s[1]:c.font=Font(bold=True);c.fill=PatternFill('solid',fgColor='D9E1F2')
    for row in s:
        for c in row:
            if isinstance(c.value,str):c.data_type='s'
            elif c.value is not None:c.number_format='#,##0.##########' if c.value!=int(c.value) else '#,##0'
    for col in 'ABCDEFG':s.column_dimensions[col].width=30 if col in 'ABG' else 19
    for row in s.iter_rows(min_row=2):
        for index in (2,3,4):row[index].alignment=Alignment(horizontal='right')
        row[5].alignment=Alignment(horizontal='center')
    s.freeze_panes='A2';s.auto_filter.ref=s.dimensions
    summary=w.create_sheet('요약');summary.append(['항목','건수'])
    for label,key in [('검증 대상','total'),('일치','matched'),('차이 또는 확인필요','mismatched')]:summary.append([label,result[key]])
    summary.append(['참고','빈 금액은 0원으로 비교하며 양쪽 모두 절댓값 1원 미만인 항목은 제외합니다.'])
    summary.column_dimensions['A'].width=26;summary.column_dimensions['B'].width=90
    w.save(path);w.close();return path


from loading_ui import center_loading_window,LoadingIndicator


class Jobs:
    def __init__(self,window,status,show_loading=True):
        self.show_loading=show_loading
        window._work_status=status
        self.window=window;self.status=status;self.busy=False;self.messages=queue.Queue();self.controls=[]
        window.protocol('WM_DELETE_WINDOW',lambda:None if self.busy else window.destroy())
    def run(self,work,done):
        if self.busy:return
        self.busy=True
        self.states=[(widget,widget.cget('state')) for widget in self.controls]
        for widget,_ in self.states:widget.configure(state='disabled')
        self.status.set('자료 처리 중…')
        loading=LoadingIndicator(self.window,self.status)
        loading.start()
        def worker():
            try:self.messages.put((True,work()))
            except Exception as e:self.messages.put((False,e))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            try:ok,result=self.messages.get_nowait()
            except queue.Empty:self.window.after(100,poll);return
            self.busy=False
            loading.close()
            for widget,state in self.states:widget.configure(state=state)
            if ok:
                try:done(result)
                except Exception as e:self.status.set('결과 표시 확인 필요');messagebox.showerror('결과 확인',str(e),parent=self.window)
            else:self.status.set('자료 확인 필요');messagebox.showerror('처리 중단',str(result),parent=self.window)
        self.window.after(100,poll)


def table(parent,columns,cell_grid=False,auto_scroll=False,horizontal_scroll=True,*,column_preferences=True):
    body=ttk.Frame(parent);body.pack(fill='both',expand=True)
    from statement_grid import StatementGrid
    from numeric_tree import NumericTreeview
    tree_class=StatementGrid if cell_grid else NumericTreeview
    tree=tree_class(body,columns=columns,show='headings',height=10,column_preferences=column_preferences)
    y=ttk.Scrollbar(body,orient='vertical',command=tree.yview);x=ttk.Scrollbar(body,orient='horizontal',command=tree.xview)
    scroll_positions={}
    def scroll_changed(scrollbar,*values):
        position=tuple(map(float,values))
        if scroll_positions.get(scrollbar)==position:return
        scroll_positions[scrollbar]=position
        scrollbar.set(*values)
        if auto_scroll:
            if float(values[0])<=0 and float(values[1])>=1:scrollbar.grid_remove()
            else:scrollbar.grid()
        if cell_grid:tree.refresh_grid()
        tree.refresh_numbers()
    tree.configure(yscrollcommand=lambda *v:scroll_changed(y,*v),
                   xscrollcommand=lambda *v:scroll_changed(x,*v))
    body.rowconfigure(0,weight=1);body.columnconfigure(0,weight=1)
    tree.grid(row=0,column=0,sticky='nsew');y.grid(row=0,column=1,sticky='ns')
    if horizontal_scroll:x.grid(row=1,column=0,sticky='ew')
    else:x.destroy();tree.configure(xscrollcommand=None)
    for c in columns:tree.heading(c,text=c);tree.column(c,width=180,minwidth=70,stretch=False)
    tree.tag_configure('attention',background='#644C20',foreground='#FFFFFF')
    return tree


def open_statement_view(parent,desktop,center,open_file):
    from statement_database import discover_statements,load_record,export_source
    from statement_catalog import column_anchor,amount_text
    from statement_exporter import _build_filtered_sheets,TYPE_LABEL,SCOPE_SUFFIX,export_statement_excel
    window=tk.Toplevel(parent,show_on_create=False);window.title('재무제표 조회 · Excel 저장');dark_titlebar(window)
    center(window,min(1320,window.winfo_screenwidth()-40),min(760,window.winfo_screenheight()-90))
    frame=ttk.Frame(window,padding=12);frame.pack(fill='both',expand=True)
    status=tk.StringVar(value='조회 화면 준비 완료 · 회계연도 자료 확인 대기');jobs=Jobs(window,status)
    paths={};bundle={};source=None;year=''
    selected_year=tk.StringVar();kind=tk.StringVar(value='자금계산서');scope=tk.StringVar(value='전체');part=tk.StringVar(value='all')
    toolbar=ttk.Frame(frame);toolbar.pack(fill='x',pady=(0,8))
    from responsive_ui import wrapping_row
    top=wrapping_row(toolbar);top.pack(fill='x',pady=(0,6))
    files=ttk.Frame(top);files.pack(side='left',anchor='n',padx=(0,12),pady=4)
    ttk.Label(files,text='회계연도',style='Accent.TLabel').pack(anchor='w',pady=(0,4))
    year_selector=ttk.Combobox(files,textvariable=selected_year,state='readonly',width=8)
    year_selector.pack(fill='x');year_selector._q.setAccessibleName('회계연도');jobs.controls.append(year_selector)
    tree=None;preferred_widths={};fit_job=None
    def fit_columns():
        nonlocal fit_job
        fit_job=None
        if tree is None or not preferred_widths:return
        tree.fit_to_viewport(preferred_widths,3 if reverse_types[kind.get()]=='trial' else 0)
    def schedule_fit(event=None):
        nonlocal fit_job
        if fit_job is not None:window.after_cancel(fit_job)
        fit_job=window.after(50,fit_columns)
    render_job=None;render_generation=0;render_states=[]
    rendering=LoadingIndicator(window,status)
    def stop_render():
        nonlocal render_job,render_generation,render_states,fit_job
        rendering.close()
        render_generation+=1
        if fit_job is not None:window.after_cancel(fit_job);fit_job=None
        if render_job is not None:window.after_cancel(render_job);render_job=None
        for widget,state in render_states:
            if widget.winfo_exists():widget.configure(state=state)
        render_states=[]
    def render(sheets,type_key):
        nonlocal render_job,render_states
        import time
        from statement_catalog import subject_display
        stop_render();generation=render_generation
        tree.delete(*tree.get_children());preferred_widths.clear()
        if not sheets:status.set('선택한 구분에 해당하는 시트가 없습니다.');return
        rendering.start()
        sheet=sheets[0];headers=sheet['headers'];cols=[str(i) for i in range(len(headers))]
        tree.configure(columns=cols)
        metrics=tkfont.Font(font=('맑은 고딕',10,'bold'))
        measured=[metrics.measure(str(h))+30 for h in headers]
        subject_column=3 if type_key=='trial' else 0
        for c,h in zip(cols,headers):tree.heading(c,text=h);tree.column(c,anchor=column_anchor(type_key,int(c)))
        render_states=[(w,w.cget('state')) for w in jobs.controls]
        for w,_ in render_states:w.configure(state='disabled')
        rows=sheet['rows'];index=0
        def append_chunk():
            nonlocal index,render_job,render_states
            render_job=None
            if not window.winfo_exists() or generation!=render_generation:return
            deadline=time.perf_counter()+.006;count=0
            while index<len(rows):
                row=rows[index];values=list(row['values'])
                for c,value in enumerate(values[:len(headers)]):measured[c]=max(measured[c],metrics.measure(str(value))+30)
                if values and not sheet['is_trial']:values[0]=subject_display(row)
                tree.insert('','end',values=values,tags=(row.get('class',''),));index+=1;count+=1
                if count>=40 or time.perf_counter()>=deadline:break
            if index<len(rows):
                status.set(f'{year}년 · {sheet["name"]} · 표 표시 중 {index:,}/{len(rows):,}행')
                render_job=window.after(1,append_rows)
            else:
                for c,value in zip(cols,measured):
                    width=300 if int(c)==subject_column else 110
                    preferred_widths[c]=width;tree.column(c,width=width,minwidth=width,stretch=False)
                schedule_fit()
                for widget,state in render_states:
                    if widget.winfo_exists():widget.configure(state=state)
                render_states=[]
                status.set(f'{year}년 · {sheet["name"]} · {len(rows):,}행')
                rendering.close()
        def append_rows():
            try:append_chunk()
            except Exception as exc:
                stop_render();status.set('표 표시 확인 필요');messagebox.showerror('조회 결과 확인',str(exc),parent=window)
        status.set(f'{year}년 · {sheet["name"]} · 표 구성 중…')
        render_job=window.after(1,append_rows)
    def display(*_):
        if not bundle or jobs.busy:return
        stop_render()
        snapshot=bundle;requested=year;type_key=reverse_types[kind.get()];scope_key=reverse_scope[scope.get()];part_key=part.get()
        jobs.run(lambda:_build_filtered_sheets(snapshot,requested,type_key,scope_key,part_key),lambda sheets:render(sheets,type_key))
        status.set(f'{requested}년 · 조회 구분 준비 중…')
    def load_year():
        nonlocal bundle,source,year
        if jobs.busy:return
        stop_render();source=None;bundle={};tree.delete(*tree.get_children())
        requested=selected_year.get();path=paths.get(requested)
        if path is None:return
        def done(record):
            nonlocal bundle,source,year
            year=requested;source=path;bundle={'by_year':{year:record}};display()
        jobs.run(lambda:load_record(path),done)
        status.set(f'{requested}년 · 재무제표 읽는 중…')
    def refresh_years():
        nonlocal paths,bundle,source,year
        if jobs.busy:return
        stop_render();year_selector.configure(values=[]);bundle={};source=None;year='';tree.delete(*tree.get_children())
        def discovered(found):
            nonlocal paths
            paths=found;year_selector.configure(values=list(paths))
            if not paths:
                selected_year.set('');status.set('저장된 재무제표가 없습니다.');return
            if selected_year.get() not in paths:selected_year.set(next(iter(paths)))
            load_year()
        paths={}
        jobs.run(discover_statements,discovered)
        status.set('저장된 회계연도 확인 중…')
    window.bind('<Destroy>',lambda event:stop_render() if event.widget is window else None,add='+')
    year_selector.bind('<<ComboboxSelected>>',lambda event:load_year())
    actions=ttk.Frame(top);actions.pack(side='right',anchor='n')
    refresh_button=ttk.Button(actions,text='연도 새로고침',command=refresh_years,padding=(8,7))
    refresh_button.pack(side='left',padx=(0,6));jobs.controls.append(refresh_button)
    controls=ttk.Frame(top);controls.pack(side='left',anchor='n')
    reverse_types={v:k for k,v in TYPE_LABEL.items()};reverse_scope={v:k for k,v in SCOPE_SUFFIX.items()}
    groups=[]
    for title in ('구분','단위','범위'):
        group=ttk.Frame(controls);group.pack(side='left',padx=(0,8));groups.append(group)
        ttk.Label(group,text=title,style='Accent.TLabel').pack(anchor='w',pady=(0,4))
    kind_selector=ttk.Combobox(groups[0],textvariable=kind,values=list(reverse_types),state='readonly',width=15)
    scope_selector=ttk.Combobox(groups[1],textvariable=scope,values=list(reverse_scope),state='readonly',width=10)
    part_label=tk.StringVar(value='전체')
    part_selector=ttk.Combobox(groups[2],textvariable=part_label,state='readonly',width=13)
    for title,selector in zip(('구분','단위','범위'),(kind_selector,scope_selector,part_selector)):
        selector.pack(fill='x');selector._q.setAccessibleName(title);jobs.controls.append(selector)
    def update_parts():
        part.set('all')
        if reverse_types[kind.get()]=='trial':groups[2].pack_forget()
        else:
            groups[2].pack(side='left',padx=(0,8))
            labels=('자산','부채와기본금') if reverse_types[kind.get()]=='balance' else ('수입','지출')
            part_selector.configure(values=['전체',*labels])
        part_label.set('전체');part_selector.current(0)
        display()
    def select_part(event=None):
        part.set(('all','upper','lower')[part_selector.current()]);display()
    kind_selector.bind('<<ComboboxSelected>>',lambda event:update_parts())
    scope_selector.bind('<<ComboboxSelected>>',display)
    part_selector.bind('<<ComboboxSelected>>',select_part)
    update_parts()
    actions.pack_forget();actions.pack(side='left',anchor='n')
    def saved(path):
        status.set(f'저장 완료: {path}')
        try:open_file(path)
        except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{path}\n{e}',parent=window)
    def export(full=False):
        if source is None:messagebox.showinfo('자료 선택','먼저 회계연도를 선택하세요.',parent=window);return
        target=output_path(source,'재무제표 연도 전체' if full else '재무제표 조회')
        if full:
            def work():
                from statement_print_export import ExcelExportWorker
                with export_source(source) as snapshot:
                    worker=ExcelExportWorker(snapshot,str(target));result=[];worker.finished.connect(lambda ok,msg:result.append((ok,msg)));worker.run()
                if not result or not result[-1][0]:raise ValueError(result[-1][1] if result else 'Excel 저장에 실패했습니다.')
                return target
        else:
            args=(bundle,source.parent,year,reverse_types[kind.get()],reverse_scope[scope.get()],part.get())
            def work():return export_statement_excel(*args,output_path=target)
        jobs.run(work,saved)
    for title,full in [('현재 화면 Excel 저장',False),('연도 전체 Excel 저장',True)]:
        button=ttk.Button(actions,text=title,command=lambda all_=full:export(all_),padding=(8,7));button.pack(side='left',padx=(0,6));jobs.controls.append(button)
    def align_toolbar(event=None):
        height=max(34,tk.G.QFontMetrics(tk.application().font()).height()+18)
        offset=tk.G.QFontMetrics(tk.application().font()).height()+8
        actions._q.setContentsMargins(0,offset,0,4)
        actions._q.setMinimumHeight(offset+height+4)
        if actions._q.layout():actions._q.layout().invalidate()
        for control in (year_selector,kind_selector,scope_selector,part_selector,*[w for w in actions.winfo_children() if isinstance(w,ttk.Button)]):control._q.setFixedHeight(height)
    window.bind('<<ThemeChanged>>',align_toolbar,add='+');align_toolbar()
    legend=ttk.Frame(frame);legend.pack(fill='x',pady=(0,6))
    from statement_grid import ROW_COLORS,SELECTION_COLOR
    palette=[(tag,label,ROW_COLORS[tag],bold) for tag,label,bold in [('gwan','관',True),('hang','항',True),('mok','목',False),('total_green','합계',True)]]
    for tag,label,color,bold in palette:
        badge=tk.Label(legend,text=f'  {label}  ',font=('맑은 고딕',9,'bold' if bold else 'normal'))
        badge._q.setStyleSheet(f'background-color:{color}; color:#172638;');badge.pack(side='left',padx=(0,5))
        def theme_badge(event=None,badge=badge,color=color):
            from statement_grid import DARK_ROW_COLORS
            appearance=getattr(badge._root(),'_appearance',None)
            dark=appearance is not None and appearance.theme=='dark'
            background=DARK_ROW_COLORS.get(color,color) if dark else color
            foreground='#EAE5F4' if dark else '#172638'
            badge._q.setStyleSheet(f'background-color:{background};color:{foreground};')
        badge.bind('<<ThemeChanged>>',theme_badge,add='+');theme_badge()
    ttk.Label(legend,text='들여쓰기: 관 → 항 → 목   ·   선택 행: 회색',style='Muted.TLabel').pack(side='left',padx=10)
    style=ttk.Style(window)
    style.configure('Statement.Treeview',rowheight=26,font=('맑은 고딕',10))
    style.map('Statement.Treeview',background=[('selected',SELECTION_COLOR)],foreground=[('selected','#172638')])
    tree=table(frame,['과목','금액'],cell_grid=True,horizontal_scroll=False);tree.configure(style='Statement.Treeview')
    for tag,label,color,bold in palette:
        tree.tag_configure(tag,background=color,foreground='#172638',font=('맑은 고딕',10,'bold' if bold else 'normal'))
    for tag in ('marker_angle','marker_paren'):
        tree.tag_configure(tag,background='#3D4962',foreground='#E2E8F0',font=('맑은 고딕',10,'bold'))
    tree.bind('<Configure>',schedule_fit)
    tree.bind('<<ThemeChanged>>',schedule_fit)
    window.after_idle(window._q.show)
    window.after(100,refresh_years)


def open_statement_verify(parent,desktop,center,open_file,appendix=False):
    from statement_compare import STATEMENT_CONFIG,build_combined_statement_verify_workbook
    from statement_appendix import run_statement_appendix_verification
    title='재무제표/부속명세서 검증' if appendix else '합산재무제표 검증'
    window=tk.Toplevel(parent);window.title(title);dark_titlebar(window)
    center(window,1080,min(730,window.winfo_screenheight()-90))
    frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True)
    status=tk.StringVar(value='원본 파일을 선택하세요. 결과를 저장한 뒤 자동으로 엽니다.');jobs=Jobs(window,status)
    footer=ttk.Frame(frame);footer.pack(side='bottom',fill='x',pady=(10,0))
    ttk.Label(footer,textvariable=status,wraplength=1000,style='Muted.TLabel').pack(anchor='w')
    ttk.Label(frame,text=title,style='Section.TLabel').pack(anchor='w',pady=(0,12))
    paths=[];last_result=None;last_target=None
    if appendix:
        year_bar=ttk.Frame(frame);year_bar.pack(fill='x',pady=(0,8))
        ttk.Label(year_bar,text='회계연도').pack(side='left',padx=(0,8))
        selected_year=tk.StringVar()
        year_box=ttk.Combobox(year_bar,textvariable=selected_year,state='readonly',width=10)
        year_box.pack(side='left');jobs.controls.append(year_box)
        def connect_year(event=None):
            nonlocal last_result,last_target
            from statement_database import discover_statements
            from appendix_view import SOURCES
            if jobs.busy:return
            tree.delete(*tree.get_children());last_result=None;last_target=None
            excel.configure(state='disabled')
            for var in paths:var.set('')
            try:
                years=discover_statements()
                attached={name:discover_statements(database) for name,database in SOURCES.items()}
                years={year:source for year,source in years.items() if any(year in items for items in attached.values())}
                year_box.configure(values=list(years))
                if selected_year.get() not in years:selected_year.set(next(iter(years),''))
                if not years:status.set('저장된 재무제표와 부속명세서가 없습니다.');return
                year=selected_year.get()
                sources=[years[year],attached['재무상태표'].get(year),attached['운영계산서'].get(year)]
                for var,source in zip(paths,sources):var.set(str(source.database) if source else '')
                status.set(f'{year}년 저장 자료를 연결했습니다. 검증 실행을 누르세요.')
            except Exception as e:messagebox.showerror('자료 연결',str(e),parent=window)
        year_box.bind('<<ComboboxSelected>>',connect_year)
        refresh=ttk.Button(year_bar,text='연도 새로고침',command=connect_year);refresh.pack(side='left',padx=8);jobs.controls.append(refresh)
        window.after(100,connect_year)
    labels=['재무제표','재무상태표 부속명세서 (선택)','운영계산서 부속명세서 (선택)'] if appendix else ['합산재무제표','대학재무제표']
    form=ttk.Frame(frame)
    if not appendix:form.pack(fill='x')
    form.columnconfigure(1,weight=1)
    for i,label in enumerate(labels):
        var=tk.StringVar();paths.append(var)
        ttk.Label(form,text=label).grid(row=i,column=0,sticky='w',padx=(0,10),pady=6)
        entry=ttk.Entry(form,textvariable=var);entry.grid(row=i,column=1,sticky='ew',pady=6);jobs.controls.append(entry)
        def choose(target=var):
            p=filedialog.askopenfilename(parent=window,initialdir=str(desktop()/'settings'),filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
            if p:target.set(p)
        button=ttk.Button(form,text='선택',command=choose);button.grid(row=i,column=2,padx=(8,0));jobs.controls.append(button)
    mode=tk.StringVar(value='자금계산서 검증');modes={c['title']:k for k,c in STATEMENT_CONFIG.items()}
    if not appendix:
        box=ttk.Combobox(frame,textvariable=mode,values=list(modes),state='readonly');box.pack(anchor='w',pady=10);jobs.controls.append(box)
        ttk.Label(frame,text='자금계산서는 C↔I열 절댓값, 재무상태표·운영계산서는 C↔E열을 비교합니다.',style='Muted.TLabel').pack(anchor='w')
    else:ttk.Label(frame,text='빈 금액은 0원으로 비교합니다. 차이가 있거나 시트가 없으면 확인필요로 표시합니다.',style='Muted.TLabel').pack(anchor='w',pady=8)
    cols=['구분','과목','재무제표','비교 금액','차이','결과'] if appendix else ['과목','대학 금액','합산 금액','차이','결과','비고']
    def execute():
        nonlocal last_result,last_target
        selected=[v.get().strip() for v in paths]
        if not selected[0] or (not appendix and not selected[1]) or (appendix and not any(selected[1:])):
            messagebox.showinfo('자료 선택','선택 연도의 저장된 재무제표와 부속명세서를 확인하세요.' if appendix else '필수 원본 파일을 선택하세요.',parent=window);return
        tree.delete(*tree.get_children());target=output_path(selected[0],title);selected_mode=modes[mode.get()]
        if appendix:
            last_result=None;last_target=None;excel.configure(state='disabled')
        year_to_verify=selected_year.get() if appendix else None
        def work():
            if appendix:
                from contextlib import ExitStack
                from statement_database import StatementSource,export_source
                with ExitStack() as stack:
                    snapshots=[str(stack.enter_context(export_source(StatementSource(Path(path),year_to_verify)))) if path else None for path in selected]
                    result=run_statement_appendix_verification('.',*snapshots)
                return target,result
            return build_combined_statement_verify_workbook(selected_mode,*selected,str(target))
        def done(value):
            nonlocal last_result,last_target
            path,result=value
            if appendix:
                last_result=result;last_target=path;excel.configure(state='normal')
            for item in result['items']:
                if appendix:
                    missing=item['fs_amount'] is None or item['supp_amount'] is None
                    values=[item['category'],item['account'],item['fs_amount'],item['supp_amount'],None if missing else item['diff'],'일치' if item['is_match'] else '확인필요']
                else:values=[item['key'],item['school_amount'],item['combined_amount'],item['diff_amount'],'일치' if item['is_match'] else '확인필요',item['note']]
                from statement_catalog import amount_text
                numeric_columns=(2,3,4) if appendix else (1,2,3)
                for index in numeric_columns:values[index]=amount_text(values[index])
                tree.insert('','end',values=['' if v is None else v for v in values],tags=() if item['is_match'] else ('attention',))
            total=result.get('total',result.get('total_items'));matched=result.get('matched',result.get('matched_items'))
            status.set(f'{total}건 중 일치 {matched}건 · 차이/확인필요 {total-matched}건'+(' · 엑셀로 열기에서 결과를 저장하고 열 수 있습니다.' if appendix else f' · {path}'))
            if not appendix:
                try:open_file(path)
                except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{path}\n{e}',parent=window)
        jobs.run(work,done)
    actions=ttk.Frame(frame);actions.pack(fill='x',pady=10)
    def open_excel():
        if last_result is None or jobs.busy:return
        snapshot=last_result;target=last_target
        def save():export_appendix(snapshot,target);return target
        def opened(path):
            status.set(f'검증 결과 저장 완료 · {path}')
            try:open_file(path)
            except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{path}\n{e}',parent=window)
        jobs.run(save,opened)
    if appendix:
        excel=ttk.Button(actions,text='엑셀로 열기',command=open_excel,state='disabled');excel.pack(side='right',padx=(8,0));jobs.controls.append(excel)
    run=ttk.Button(actions,text='검증 실행' if appendix else '검증 · 결과 저장',command=execute,style='Primary.TButton');run.pack(side='right');jobs.controls.append(run)
    tree=table(frame,cols)
    for index in ((2,3,4) if appendix else (1,2,3)):tree.column(cols[index],anchor='e')
    tree.column('결과',anchor='center')
    if appendix:
        tree.tag_configure('attention',background='#FDE8E8',foreground='#7F1D1D')
        tree._q.setSortingEnabled(False);tree.proxy.sort(-1)
        tree._q.horizontalHeader().setSectionsClickable(False)
        tree._q.horizontalHeader().setSortIndicatorShown(False)
