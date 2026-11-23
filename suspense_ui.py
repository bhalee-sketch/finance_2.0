"""Qt suspense review: background jobs, paged evidence and scoped approvals."""
from copy import deepcopy
from pathlib import Path
import queue
import threading
import qt_ui as tk
from qt_ui import ttk,filedialog,messagebox
from suspense_data import load_ledger,sheet_names,FIELDS,parse_date
from suspense_engine import run,Cancelled,validate,Candidate
from suspense_manual import open_match,open_reassignment,apply_manual_match
from suspense_store import load_settings,save_settings,action,add_alias,change_counterparty_rule
from suspense_export import summary,department_rows,ordered_group,export_visible_view
from result_paths import result_path
from statement_ui import table
from ui_theme import dark_titlebar
from responsive_ui import wrapping_row

TABS=('매칭내역','미매칭 잔여','부서별 현황','거래처 규칙','예외 규칙 관리','원본 전체')
RESIDUAL_COLUMNS=('번호','선택','회계단위','부서코드','회계일자','거래처명','적요','금액','정산금액','잔액','예적금정보')
RESIDUAL_WIDTHS=(70,70,90,130,95,165,350,145,145,145,215)


def residual_amount_totals(items):
    return tuple(sum(int(str(item['values'][index]).replace(',','') or 0) for item in items) for index in (8,9,10))


def fit_residual_columns(tree):
    """Keep the reference column proportions independent of the displayed rows."""
    tree.configure(displaycolumns=RESIDUAL_COLUMNS)
    tree._width_preferences.locked.clear()
    available=max(1,tree._q.viewport().width())
    total=sum(RESIDUAL_WIDTHS)
    widths=[int(available*weight/total) for weight in RESIDUAL_WIDTHS]
    widths[-1]+=available-sum(widths)
    for column,width in zip(RESIDUAL_COLUMNS,widths):
        tree.column(column,width=width,minwidth=1,stretch=False)
    header=tree._q.horizontalHeader()
    header.setSectionsMovable(False)
    header.setSectionResizeMode(tk.W.QHeaderView.ResizeMode.Fixed)
    header.setContextMenuPolicy(tk.C.Qt.ContextMenuPolicy.NoContextMenu)
    header.setToolTip('고정 열 배치')


def visible_matching_rows(result,tab,passes):
    """A filter selects groups, never hides the matched counterpart or zero residuals."""
    byid={t.row_id:t for t in result['ledger']['rows']}
    return [(byid[i],g) for g in result['groups']
            if (tab in ('전체 매칭','매칭내역') or g.state==tab) and any(passes(byid[j]) for j in g.ids)
            for i in ordered_group(g,byid)]


def open_suspense(parent,desktop,center,open_file):
    window=tk.Toplevel(parent);window.title('가수금 정산검증');dark_titlebar(window);center(window,1250,820)
    body=ttk.Frame(window,padding=14);body.pack(fill='both',expand=True)
    settings_path=desktop()/'settings'/'suspense'/'approvals.json'
    try:settings=load_settings(settings_path)
    except (ValueError,OSError) as exc:messagebox.showerror('승인 설정 확인',str(exc),parent=window);window.destroy();return
    path=tk.StringVar();sheet=tk.StringVar();status=tk.StringVar(value='가수금 원장을 선택하고 정산검증 실행을 누르세요. 원본 파일은 변경하지 않습니다.')
    window._work_status=status
    overview=tk.StringVar(value='원본 · 자동 · 조건부 · 미매칭 · 그룹 · 잔액을 검증 후 표시합니다.')
    controls=[];result=None;busy=False;messages=queue.Queue();cancel=threading.Event();shown=[];baseline=None;checked=set();draw_job=None;draw_generation=0
    source=wrapping_row(body);source.pack(fill='x')
    filegroup=ttk.Frame(source);filegroup.pack(side='left')
    ttk.Label(filegroup,text='원장 파일').pack(side='left',padx=(0,6))
    entry=ttk.Entry(filegroup,textvariable=path,state='readonly',width=38);entry.pack(side='left');controls.append(entry)
    entry._q.setMinimumWidth(240);entry._q.setAccessibleName('원장 파일 경로');entry._q.setPlaceholderText('Excel 원장을 선택하세요')
    path.trace_add('write',lambda *_:entry._q.setToolTip(path.get()))
    sheetgroup=ttk.Frame(source);sheetgroup.pack(side='left')
    ttk.Label(sheetgroup,text='시트').pack(side='left',padx=(0,6))
    sheetbox=ttk.Combobox(sheetgroup,textvariable=sheet,state='readonly',width=14);sheetbox.pack(side='left',padx=6);controls.append(sheetbox)
    def choose_file(value=None):
        nonlocal result,baseline
        if busy:return
        value=value or filedialog.askopenfilename(parent=window,title='가수금 원장',filetypes=[('Excel 원장','*.xls *.xlsx')])
        if not value:return
        def done(names):
            nonlocal result,baseline
            if cancel.is_set():status.set('파일 선택을 취소했습니다.');return
            if not names:raise ValueError('선택한 원장에 시트가 없습니다.')
            path.set(value);sheetbox.configure(values=names);sheet.set(names[0])
            result=None;baseline=None;overview.set('선택한 원장의 정산검증을 실행하세요.');refresh()
            status.set('시트를 확인한 뒤 정산검증 실행을 누르세요.')
        status.set('원장의 시트 목록을 읽고 있습니다…')
        launch(lambda:sheet_names(value),done)
    def button(parent,title,command,side='left'):
        widget=ttk.Button(parent,text=title,command=command);widget.pack(side=side,padx=3);controls.append(widget);return widget
    button(source,'파일 선택',choose_file)
    try:
        DND_FILES='DND_Files'
        entry.drop_target_register(DND_FILES)
        def drop(event):
            names=window.tk.splitlist(event.data)
            if len(names)==1:choose_file(names[0])
            else:messagebox.showinfo('파일 선택','한 번에 원장 한 개를 선택하세요.',parent=window)
        entry.dnd_bind('<<Drop>>',drop)
    except (ImportError,AttributeError,tk.TclError):pass
    entry.bind('<FocusOut>',lambda e: choose_file(path.get()) if path.get() and not sheet.get() else None)
    reviewbar=wrapping_row(body);reviewbar.pack(fill='x',pady=(0,8))
    summary_label=ttk.Label(body,textvariable=overview,style='Accent.TLabel',wraplength=1180);summary_label.pack(fill='x',pady=(0,8))
    body.bind('<Configure>',lambda event:summary_label.configure(wraplength=max(280,event.width-28)),add='+')
    filterarea=ttk.Frame(body);filterarea.pack(fill='x',pady=(0,6))
    filters=wrapping_row(filterarea);filters.pack(fill='x')
    filtervars={}
    for label,width in [('부서',12),('거래선',12),('적요',16),('시작일',10),('종료일',10),('금액',12)]:
        group=ttk.Frame(filters);group.pack(side='left')
        ttk.Label(group,text=label).pack(side='left',padx=(0,4));var=tk.StringVar();filtervars[label]=var
        widget=ttk.Entry(group,textvariable=var,width=width);widget.pack(side='left');controls.append(widget)
        widget._q.setAccessibleName(label);widget.bind('<Return>',lambda event:refresh())
        if label in ('시작일','종료일'):widget._q.setPlaceholderText('YYYY-MM-DD')
    tabarea=ttk.Frame(body);tabarea.pack(fill='both',expand=True)
    ttk.Style(window).configure('Suspense.TNotebook',tabmargins=(0,0,190,0))
    notebook=ttk.Notebook(tabarea,style='Suspense.TNotebook');notebook.pack(fill='both',expand=True)
    frames={};trees={}
    columns=('구분','매칭번호','판정','유형','전표정보','회계일자','부서명','거래선','차변','대변','적요','원본행','배분','차변 잔여','대변 잔여','탐색 상태')
    for name in TABS:
        frame=ttk.Frame(notebook);notebook.add(frame,text=name);frames[name]=frame
        custom={'미매칭 잔여':('번호','선택','회계단위','부서코드','회계일자','거래처코드','거래처명','적요','금액','정산금액','잔액','예적금정보'),
                '검토 후보':('후보번호','유형','판정','점수','대변합계','차변합계','원본행','근거'),
                '매칭 그룹검산':('매칭번호','판정','유형','배분 차변','배분 대변','차이','점수','근거'),
                '부서별 현황':('부서','잔여 건수','순잔액(대변−차변)'),
                '정산 재배정 이력':('동작','원본행/ID','승인자·근거','시각'),
                '단계별 매칭 실적':('항목','건수·결과'),
                '거래처 규칙':('원본 거래처','대응 거래처','적용 부서'),
                '예외 규칙 관리':('구분','규칙ID','상태','별칭','기간','부서','승인자','목적·근거')}
        trees[name]=table(frame,custom.get(name,columns))
        trees[name]._q.setProperty('compactRows',True)
        from suspense_table import configure_detail_table
        configure_detail_table(trees[name])
        if name=='미매칭 잔여':
            from check_list import CenteredCheckDelegate
            view=trees[name]._q
            view.setItemDelegateForColumn(1,CenteredCheckDelegate(view))
        widths={'구분':55,'매칭번호':155,'판정':100,'유형':75,'전표정보':100,'회계일자':95,'부서명':100,'거래선':110,'차변':110,'대변':110,'적요':260,'원본행':65,'배분':110,'차변 잔여':110,'대변 잔여':110,'탐색 상태':170}
        if name=='거래처 규칙':
            for col in custom[name]:trees[name].column(col,width=260,stretch=True)
        if name=='예외 규칙 관리':
            for col,width in zip(custom[name],(80,80,50,150,90,85,75,450)):
                trees[name].column(col,width=width,minwidth=50,stretch=(col=='목적·근거'))
        if name=='부서별 현황':
            for col in ('잔여 건수','순잔액(대변−차변)'):trees[name].column(col,anchor='e')
        if name=='미매칭 잔여':
            trees[name].configure(displaycolumns=RESIDUAL_COLUMNS)
            for col in custom[name]:
                trees[name].column(col,width=130 if col in ('금액','정산금액','잔액') else 260 if col=='적요' else 180 if col=='예적금정보' else 110,anchor='e' if col in ('금액','정산금액','잔액') else 'w')
            for col in ('번호','선택'):trees[name].column(col,width=48,stretch=False,anchor='center')
        if name not in custom:
            for column,width in widths.items():trees[name].column(column,width=width,minwidth=45,anchor='e' if column in ('차변','대변','배분','차변 잔여','대변 잔여') else 'w')
            trees[name].configure(displaycolumns=('판정','회계일자','부서명','거래선','차변','대변','적요','매칭번호','전표정보','유형','원본행','배분','차변 잔여','대변 잔여','구분','탐색 상태'))
    layout_job=None
    def fit_current(event=None):
        nonlocal layout_job
        if layout_job is not None:window.after_cancel(layout_job)
        for t in trees.values():
            job=getattr(t,'_layout_warm_job',None)
            if job is not None:t.after_cancel(job);t._layout_warm_job=None
        def apply():
            nonlocal layout_job
            layout_job=None
            tree=trees[active()]
            display=list(tree['displaycolumns'])
            if display==['#all']:display=list(tree['columns'])
            available=max(1,tree._q.viewport().width())
            if active()=='미매칭 잔여':fit_residual_columns(tree)
            else:
                width=max(1,available//max(1,len(display)))
                for index,col in enumerate(display):
                    tree.column(col,width=width+(available-width*len(display) if index==len(display)-1 else 0),minwidth=1,stretch=False)
            tree._wrap_cells=False;tree._q.setWordWrap(False)
            tree._q.setHorizontalScrollBarPolicy(tk.C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            tree._q.verticalHeader().setDefaultSectionSize(max(26,tk.G.QFontMetrics(tree._q.font()).height()+6))
        layout_job=window.after(100,apply)
    for tree in trees.values():tree.bind('<Configure>',fit_current,add='+')
    footer=ttk.Frame(body);footer.pack(side='bottom',fill='x',pady=5);pager=tk.StringVar()
    sum_text=tk.StringVar()
    sum_label=ttk.Label(footer,textvariable=sum_text,style='Accent.TLabel');sum_label.pack(fill='x')
    sum_label._q.setAlignment(tk.C.Qt.AlignmentFlag.AlignRight|tk.C.Qt.AlignmentFlag.AlignVCenter)
    window._residual_totals=sum_text


    def active():return notebook.tab(notebook.select(),'text')
    def selected():
        tree=trees[active()];return [shown[int(i[1:])] for i in tree.selection()]
    def passes(t):
        if any(filtervars[key].get().strip().lower() not in value.lower() for key,value in [('부서',t.department),('거래선',t.counterparty),('적요',t.description)]):return False
        start,end=filtervars['시작일'].get().strip(),filtervars['종료일'].get().strip()
        if start and t.day<parse_date(start):return False
        if end and t.day>parse_date(end):return False
        amount=filtervars['금액'].get().replace(',','').strip()
        if amount and amount not in (str(t.debit),str(t.credit)):return False
        return True
    rule_query=tk.StringVar()
    def records():
        if active()=='거래처 규칙':
            query=rule_query.get().strip().casefold()
            return [{'ids':set(),'group':None,'rule_id':a['id'],'values':(a['source'],a['target'],a['department'])} for a in settings.get('aliases',[]) if a.get('kind','counterparty')=='counterparty' and not a.get('deleted') and query in ' '.join((a['source'],a['target'],a['department'])).casefold()]
        if active()=='예외 규칙 관리':
            return [{'ids':set(),'group':None,'values':('부서 동일 취급' if a.get('kind')=='department' else '예외',a['id'],'승인' if a.get('approved') else '해제',a['source']+' → '+a['target'],(a.get('start','')+'~'+a.get('end','')) if a.get('start') or a.get('end') else '제한 없음',a.get('department',''),a.get('approver',''),a.get('purpose','')+' / '+a.get('reason',''))} for a in settings.get('aliases',[]) if a.get('kind','counterparty')!='counterparty' and not a.get('deleted')]
        if result is None:return []
        tab=active();byid={t.row_id:t for t in result['ledger']['rows']};v=result['validation'];groups=result['groups']
        owner={i:g for g in groups for i in g.ids}
        def row(t,g=None,kind='거래'):
            residual=v['residual'][t.row_id]
            state=g.state if g else '탐색 미완료' if t.row_id in result['incomplete'] else '미매칭'
            return {'ids':{t.row_id},'group':g,'values':(kind,g.id if g else '',state,g.kind if g else '',t.voucher,t.day.isoformat(),t.department,t.counterparty,f'{t.debit:,}',f'{t.credit:,}',t.description,t.row,f"{v['allocations'].get(t.row_id,0):,}",f'{residual[0]:,}',f'{residual[1]:,}',result.get('search_status',{}).get(g.id,'') if g else state)}
        if tab=='매칭내역':
            return [row(t,g) for t,g in visible_matching_rows(result,tab,passes)]
        if tab=='미매칭 잔여':
            headers=[str(h).strip() for h in result['ledger']['headers']]
            def raw(t,label):
                return t.raw[headers.index(label)] if label in headers and headers.index(label)<len(t.raw) else ''
            out=[]
            for t in sorted(result['ledger']['rows'],key=lambda t:(t.day,t.row)):
                d,c=v['residual'][t.row_id]
                if not (d or c) or not passes(t):continue
                amount=t.credit
                settled=v['allocations'].get(t.row_id,0) if t.side=='C' else d
                out.append({'ids':{t.row_id},'group':owner.get(t.row_id),'values':(len(out)+1,'☑' if t.row_id in checked else '☐',t.unit,raw(t,'부서코드') or t.department,t.day.isoformat(),raw(t,'거래처코드'),t.counterparty,t.description,f'{amount:,}',f'{settled:,}',f'{c-d:,}',t.account)})
            return out
        if tab in ('원본 전체','미매칭 잔여'):
            return [row(t,owner.get(t.row_id)) for t in result['ledger']['rows'] if passes(t) and (tab=='원본 전체' or t.row_id not in owner or any(v['residual'][t.row_id]))]
        if tab=='검토 후보':
            return [{'ids':set(g.ids),'group':g,'values':(g.id,g.kind,g.state,g.score,sum(byid[i].credit for i in g.ids),sum(byid[i].debit for i in g.ids),','.join(str(byid[i].row) for i in sorted(g.ids)),' / '.join(g.reasons))} for g in result['suggestions'] if any(passes(byid[i]) for i in g.ids)]
        if tab=='매칭 그룹검산':
            out=[]
            for g in groups:
                if not any(passes(byid[i]) for i in g.ids):continue
                alloc=dict(g.allocations) if g.allocations else {i:byid[i].value for i in g.ids};d=sum(alloc[i] for i in g.debits);c=sum(alloc[i] for i in g.credits)
                out.append({'ids':set(g.ids),'group':g,'values':(g.id,g.state,g.kind,d,c,d-c,g.score,' / '.join(g.reasons))})
            return out
        if tab=='부서별 현황':items=[(dept,f'{count:,}',f'{credit-debit:,}') for dept,total,debit,credit,count,net in department_rows(result) if count>0]
        elif tab=='정산 재배정 이력':items=[(kind,ids,reason,'') for kind,ids,reason in result['history']]+[('사용자 '+a['action'],a['id'],a['approver']+' / '+a['reason'],a['timestamp']) for a in settings.get('actions',[]) if a.get('file_hash')==result['ledger']['hash']]
        elif tab=='단계별 매칭 실적':items=[(stage,count) for stage,count in result['stages']]+[(name,'통과' if ok else '실패') for name,ok in v['checks']]
        else:items=[('부서 동일 취급' if a.get('kind')=='department' else '거래선 별칭',a['id'],'승인' if a.get('approved') else '해제',a['source']+' → '+a['target'],(a['start']+'~'+a['end']) if a.get('start') or a.get('end') else '제한 없음',a['department'],a['approver'],a['purpose']+' / '+a['reason']) for a in settings.get('aliases',[]) if a.get('kind','counterparty')!='counterparty' and not a.get('deleted')]
        return [{'ids':set(),'group':None,'values':values} for values in items]
    def draw():
        nonlocal draw_job,draw_generation
        import time
        if draw_job is not None:window.after_cancel(draw_job);draw_job=None
        draw_generation+=1;generation=draw_generation
        tree=trees[active()];tree.delete(*tree.get_children());items=shown;index=0
        if active()=='미매칭 잔여':
            amount,settled,balance=residual_amount_totals(items)
            sum_text.set(f'조회 합계   금액 {amount:,}원   |   정산금액 {settled:,}원   |   잔액 {balance:,}원')
        else:sum_text.set('')
        def append_rows():
            nonlocal index,draw_job
            draw_job=None
            if generation!=draw_generation or not tree.winfo_exists():return
            deadline=time.perf_counter()+.006
            while index<len(items):
                tree.insert('','end',iid=f'r{index}',values=items[index]['values']);index+=1
                if index%50==0 and time.perf_counter()>=deadline:break
            if index<len(items):
                pager.set(f'전체 {len(items):,}건 · {index:,}건 표시 중…')
                draw_job=window.after(1,append_rows)
            else:
                pager.set(f'전체 {len(items):,}건 · Ctrl/Shift 다중 선택 · 더블클릭 상세' if items else '표시할 내역이 없습니다. 원장 선택·검증 또는 검색 조건을 확인하세요.')
                fit_current()
        append_rows()
    def refresh(event=None):
        nonlocal shown
        try:shown=records();draw()
        except ValueError as exc:messagebox.showerror('검색 조건',str(exc),parent=window)
    def cleanup_draw(event):
        nonlocal draw_job,layout_job
        if event.widget is window and layout_job is not None:
            window.after_cancel(layout_job);layout_job=None
        if event.widget is window and draw_job is not None:
            window.after_cancel(draw_job);draw_job=None
    window.bind('<Destroy>',cleanup_draw,add='+')
    button(filters,'검색',refresh)
    def reset_filters():
        for var in filtervars.values():var.set('')
        rule_query.set('');refresh()
    button(filters,'검색 초기화',reset_filters)
    rule_filters=ttk.Frame(filterarea)
    ttk.Label(rule_filters,text='거래처·부서').pack(side='left',padx=(0,6))
    rule_search=ttk.Entry(rule_filters,textvariable=rule_query,width=32);rule_search.pack(side='left',padx=4)
    rule_search.bind('<Return>',refresh)
    button(rule_filters,'검색',refresh)
    def tab_changed(event=None):
        if active()=='거래처 규칙':filters.pack_forget();rule_filters.pack(side='left',fill='x')
        else:rule_filters.pack_forget();filters.pack(fill='x')
        refresh()
    notebook.bind('<<NotebookTabChanged>>',tab_changed)
    def check_residual(event):
        tree=trees['미매칭 잔여'];identity=tree.identify_row(event.y)
        if not identity or tree.identify_column(event.x)!='#2':return
        item=shown[int(identity[1:])];row_id=next(iter(item['ids']))
        checked.discard(row_id) if row_id in checked else checked.add(row_id)
        mark='☑' if row_id in checked else '☐'
        values=list(item['values']);values[1]=mark;item['values']=tuple(values)
        tree.set(identity,'선택',mark);return 'break'
    trees['미매칭 잔여'].bind('<Button-1>',check_residual)
    def sheet_changed(event=None):
        nonlocal result,baseline
        result=None;baseline=None;overview.set('선택한 시트의 정산검증을 실행하세요.');refresh()
    sheetbox.bind('<<ComboboxSelected>>',sheet_changed)
    def detail(event=None):
        chosen=selected()
        if active()=='거래처 규칙':edit_rule();return
        if not chosen or result is None:return
        item=chosen[0];g=item['group'];byid={t.row_id:t for t in result['ledger']['rows']}
        dialog=tk.Toplevel(window);dialog.title('정산 그룹 · 원본 근거');dark_titlebar(dialog);center(dialog,900,620)
        box=tk.Text(dialog,wrap='word');box.pack(fill='both',expand=True)
        ids=g.ids if g else item['ids']
        lines=[]
        if g:
            lines=[f'{g.id} | {g.state} | {g.kind} | 점수 {g.score}',*g.reasons,'',f'배분: {dict(g.allocations) if g.allocations else "전체 금액"}']
            rivals=[c.id for c in result['candidates'] if c.id!=g.id and c.ids&g.ids]
            lines+=['경쟁 후보: '+', '.join(rivals)]
        for identity in sorted(ids,key=lambda i:(byid[i].side!='C',byid[i].day,byid[i].voucher,byid[i].row)):
            t=byid[identity];lines+=['',f'{t.row_id} / {t.sheet} {t.row}행',f'{t.voucher} | {t.day} | {t.department} | {t.counterparty}',f'차변 {t.debit:,} / 대변 {t.credit:,} / 잔여 {result["validation"]["residual"][identity]}',f'계좌 {t.account} / 회계 {t.unit} / 대상 월 {t.months} / 기간 {t.period}',t.description,'원본: '+repr(t.raw)]
        box.insert('1.0','\n'.join(lines));box.configure(state='disabled')
    for tree in trees.values():tree.bind('<Double-1>',detail)
    from loading_ui import watch_loading
    watch_loading(window,status,lambda:busy)
    def launch(work,done):
        nonlocal busy
        if busy:return
        busy=True;cancel.clear();states=[(w,w.cget('state')) for w in controls]
        for w,_ in states:w.configure(state='disabled')
        def worker():
            try:messages.put(('done',work()))
            except Exception as exc:messages.put(('error',exc))
        threading.Thread(target=worker,daemon=True).start()
        def poll():
            nonlocal busy
            try:
                while True:
                    kind,value=messages.get_nowait()
                    if kind=='progress':status.set(value);continue
                    busy=False
                    for w,state in states:w.configure(state=state)
                    if kind=='done':
                        try:done(value)
                        except Exception as exc:status.set('결과 처리 실패');messagebox.showerror('결과 확인',str(exc),parent=window)
                    else:
                        status.set(str(value))
                        if not isinstance(value,Cancelled):messagebox.showerror('정산검증 중단',str(value),parent=window)
                    return
            except queue.Empty:window.after(100,poll)
        window.after(100,poll)
    def progress(stage,current,total):messages.put(('progress',f'{stage} · {current:,}/{total:,}'))
    def execute(updated=None,reuse=False):
        if busy:return
        if not path.get() or not sheet.get():messagebox.showinfo('원장 선택','원장 파일과 시트를 선택하세요.',parent=window);return
        snapshot=deepcopy(updated if updated is not None else settings);filename=path.get();sheetname=sheet.get()
        ledger=result['ledger'] if reuse and result else None
        def work():return run(ledger or load_ledger(filename,sheetname),snapshot,progress,cancel.is_set)
        def done(value):
            nonlocal result,settings,baseline
            result=value;baseline=None
            if value['validation']['ok']:
                snapshot.setdefault('previous',{})[value['ledger']['hash']]=[sorted(c.ids) for c in value['groups']]
                save_settings(settings_path,snapshot);settings=snapshot
            metrics=dict(summary(value))
            overview.set(
                f"추출 기준 {value['ledger']['account_filter']} · 회계일자순\n"
                f"원본 {metrics['원본 거래 건수']:,}건 · 자동 {metrics['자동매칭 행 수']:,}행 · 조건부 {metrics['조건부매칭 행 수']:,}행 · 승인 {metrics['사용자 승인 행 수']:,}행 · 미매칭 {metrics['미매칭 고유 행 수']:,}행\n"
                f"정산 {metrics['정산 그룹 수']:,}그룹 · 연결률 {metrics['전체 연결률(조건부 포함)']} · 검산 {metrics['검산']} · 탐색 미완료 {metrics['탐색 미완료 행']:,}행\n"
                f"차변 {metrics['원본 차변합계']:,}원 · 대변 {metrics['원본 대변합계']:,}원 · 잔여 순대차(차변−대변) {metrics['잔여 순대차잔액(차변−대변)']:,}원")
            refresh();status.set('검산 실패 — 정상 완료가 아닙니다.' if not value['validation']['ok'] else '탐색 미완료가 있습니다. 조건부매칭·미매칭 잔여를 확인하세요.' if value['incomplete'] else '검산 완료 · 조건부매칭은 회계상 정산 확정이 아닙니다.')
        launch(work,done)
    button(source,'정산검증 실행',execute).configure(style='Primary.TButton')
    def form(title,fields,callback,save_text="저장 및 재검증"):
        dialog=tk.Toplevel(window);dialog.title(title);dialog.transient(window);dark_titlebar(dialog)
        center(dialog,780,min(700,100+len(fields)*42))
        outer=ttk.Frame(dialog);outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,highlightthickness=0);scroll=ttk.Scrollbar(outer,command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
        panel=ttk.Frame(canvas,padding=16);item=canvas.create_window(0,0,window=panel,anchor='nw')
        panel.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width));variables={}
        for i,(label,default) in enumerate(fields):
            ttk.Label(panel,text=label).grid(row=i,column=0,sticky='w',pady=4)
            var=tk.StringVar(value=default);variables[label]=var;ttk.Entry(panel,textvariable=var,width=55).grid(row=i,column=1,padx=8,pady=4)
        def accept():
            try:callback({label:var.get().strip() for label,var in variables.items()})
            except (ValueError,OSError) as exc:messagebox.showerror(title,str(exc),parent=dialog);return
            dialog.destroy()
        ttk.Button(panel,text=save_text,command=accept).grid(row=len(fields),column=1,sticky='e',pady=8)
        dialog.grab_set()
    def persist_rules(updated):
        nonlocal settings
        save_settings(settings_path,updated);settings=updated
        if result is not None:result['settings']=updated
        refresh();status.set('규칙을 저장했습니다. 다음 정산검증 실행부터 적용됩니다. 기존 매칭은 유지합니다.')
    def alias():
        def save(values):
            updated=deepcopy(settings);add_alias(updated,*(values[k] for k in ('원본 거래처','대응 거래처','적용 부서')))
            persist_rules(updated)
        form('거래처 등록',[(label,'') for label in ('원본 거래처','대응 거래처','적용 부서')],save,save_text='등록')
    def edit_rule():
        if active()!='거래처 규칙' or not selected():return
        rule_id=selected()[0]['rule_id'];rule=next(a for a in settings['aliases'] if a['id']==rule_id)
        def save(values):
            updated=deepcopy(settings);change_counterparty_rule(updated,rule_id,*(values[k] for k in ('원본 거래처','대응 거래처','적용 부서')))
            persist_rules(updated)
        form('거래처 변경',list(zip(('원본 거래처','대응 거래처','적용 부서'),(rule['source'],rule['target'],rule['department']))),save,save_text='변경 저장')
    def delete_rule():
        if active()!='거래처 규칙' or not selected():return
        if not messagebox.askyesno('거래처 삭제','선택한 거래처 규칙을 삭제할까요? 기존 매칭은 유지됩니다.',parent=window):return
        try:
            updated=deepcopy(settings)
            for item in selected():change_counterparty_rule(updated,item['rule_id'],delete=True)
            persist_rules(updated)
        except (ValueError,OSError) as exc:messagebox.showerror('거래처 삭제',str(exc),parent=window)
    button(rule_filters,'거래처 등록',alias)
    button(rule_filters,'선택 변경',edit_rule)
    button(rule_filters,'선택 삭제',delete_rule)
    def save_manual(updated):
        nonlocal result,settings,baseline
        try:
            new_result=apply_manual_match(result,updated)
            updated.setdefault('previous',{})[result['ledger']['hash']]=[sorted(g.ids) for g in new_result['groups']]
            save_settings(settings_path,updated)
        except (OSError,ValueError) as exc:
            messagebox.showerror('매칭 저장',str(exc),parent=window);return False
        result=new_result;settings=updated;baseline=None;checked.clear()
        metrics=dict(summary(result))
        overview.set(f"원본 {metrics['원본 거래 건수']:,}건 · 사용자 승인 {metrics['사용자 승인 행 수']:,}행 · 잔여 {metrics['잔여 금액이 있는 행 수']:,}건 · 검산 {metrics['검산']} · 순잔액(대변−차변) {-result['validation']['net']:,}원")
        refresh();status.set('선택 거래 매칭을 저장했습니다. 매칭내역에서 연결 내역을 확인할 수 있습니다. 다른 자동 연결은 재검증하지 않았습니다.')
        return True
    def manual_match():
        if result is None or busy:return
        if not result['validation']['ok']:
            messagebox.showerror('매칭 실행','검산을 통과한 결과에서 실행하세요.',parent=window);return
        preselected=checked if active()=='미매칭 잔여' else ()
        open_match(window,result,settings,center,save_manual,preselected)
    def reassign():
        if result is None or busy:return
        if not result['validation']['ok']:
            messagebox.showerror('매칭 건 교체','검산을 통과한 결과에서 실행하세요.',parent=window);return
        selected_ids=checked if active()=='미매칭 잔여' and checked else set().union(*(i['ids'] for i in selected()))
        open_reassignment(window,result,settings,center,save_manual,selected_ids)
    button(reviewbar,'매칭 실행',manual_match)
    button(reviewbar,'매칭 건 교체',reassign)
    button(filters,'매칭내역 보기',detail)
    def register_exception():
        from suspense_exceptions import open_registration
        open_registration(window,settings,persist_rules,center)
    button(reviewbar,'예외규칙 등록',register_exception)
    def open_current_view():
        if result is None or busy:return
        try:
            title=active();tree=trees[title];columns=list(tree['columns'])
            display=list(tree['displaycolumns'])
            if display==['#all']:display=columns
            indexes=[columns.index(c) for c in display]
            headers=[getattr(tree,'_column_titles',{}).get(c,tree.heading(c,'text')) for c in display]
            # records() includes the entire filtered view, including rows still loading.
            data=[[item['values'][i] for i in indexes] for item in records()]
            output=result_path('가수금_'+title)
        except (ValueError,OSError) as exc:
            messagebox.showerror('현재화면 엑셀열기',str(exc),parent=window);return
        def done(p):
            status.set(f'현재화면 {len(data):,}건 · {p}')
            open_file(p)
        launch(lambda:export_visible_view(output,title,headers,data),done)
    view_button=ttk.Button(filters,text='현재화면 엑셀열기',command=open_current_view)
    view_button.pack(side='left',padx=3);controls.append(view_button)
    window.protocol('WM_DELETE_WINDOW',lambda:cancel.set() if busy else window.destroy())
    refresh()
