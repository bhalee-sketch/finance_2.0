from check_list import CheckList
"""재무분석: 원본 근거, 수입 분모 설정, 결산 구성 및 연도별 비교."""
from datetime import datetime
from decimal import Decimal
import qt_ui as tk
from qt_ui import ttk,messagebox
from pathlib import Path
from finance_ui import shell,fill,target_file,saved,compact_combo,content_widths,apply_widths
from statement_ui import table
from statement_catalog import amount_text
from financial_analysis import (SCOPES,DEFAULT_PRESET,ANALYSIS_HEADERS,analysis_rows,
    denominator,validate_preset,appendix_check,ledger_matches,export_report,trend_rows,statement_view)
from analysis_runtime import load_analysis_history as load_history
from statement_analysis import normalize
from analysis_presentation import unit_label,available_units,analysis_total,trend_total,complete_sum,pie_values,expand_to_mok,multi_trend,source_total_row,expanded_composition


def display_table(tree,headers,rows,numeric=()):
    formatted=[[round(v,2) if isinstance(v,Decimal) and ('(%)' in headers[i]) else v for i,v in enumerate(row)] for row in rows]
    fill(tree,headers,formatted,numeric)
    widths=content_widths(tree,headers,formatted);tree._analysis_widths=widths
    apply_widths(tree,widths)



def open_financial_analysis(parent,desktop,center,open_file):
    window,body,status,jobs=shell(parent,'재무분석',center,show_status=False)
    center(window,min(1440,window.winfo_screenwidth()-70),min(920,window.winfo_screenheight()-90))
    folder=desktop()/'settings'/'finance statement'
    history={};sources={};issues=[];preset=validate_preset(DEFAULT_PRESET)
    shown=[];trend=[];series_paths=[];series_headers=['연도'];series_rows=[];series_context=None;checks=[];check_notes=[];checked_year=None;denom_details=[]
    expanded=set();expand_depth=tk.IntVar(value=1)
    statement=tk.StringVar(value='자금계산서')
    selected=tk.StringVar();scope=tk.StringVar(value='전체');unit=tk.StringVar(value='합계');section=tk.StringVar(value='지출')
    filters={key:tk.StringVar(value='전체') for key in ('관','항','목')}
    style=ttk.Style(window)
    style.configure('Dashboard.TLabelframe',background='#192131',bordercolor='#395570',relief='solid',borderwidth=1)
    style.configure('Dashboard.TLabelframe.Label',background='#192131',foreground='#E5F0FA',font=('맑은 고딕',11,'bold'))
    style.configure('Dashboard.Treeview',rowheight=25,background='#192738',fieldbackground='#192738',foreground='#E7EDF6')
    style.configure('Dashboard.Treeview.Heading',background='#253C54',foreground='#E7EDF6',font=('맑은 고딕',9,'bold'),padding=5)
    style.map('Dashboard.Treeview',background=[('selected','#245B70')],foreground=[('selected','#FFFFFF')])
    toolbar=ttk.Frame(body);toolbar.pack(fill='x',pady=(0,10))
    ttk.Label(toolbar,text='▥  대학 재무분석 시스템   |   재무분석',style='Section.TLabel').pack(side='left')
    actions=ttk.Frame(toolbar);actions.pack(side='right')
    from responsive_ui import wrapping_row
    top=wrapping_row(body);top.pack(fill='x',pady=(0,6));controls={}
    unit_choice=tk.StringVar(value=unit_label(unit.get()))
    selections={'회계연도':selected,'재무제표':statement,'회계구분':scope,
                '단위':unit_choice,'범위':section,**filters}
    for title,var in selections.items():
        group=ttk.LabelFrame(top,text=title,padding=3);group.pack(side='left')
        box=ttk.Combobox(group,textvariable=var,state='readonly',width=9)
        box._q.setAccessibleName(title)
        box.pack(fill='x');controls[title]=box;jobs.controls.append(box)
    year_box=controls['회계연도']
    compact_combo(controls['재무제표'],['자금계산서','재무상태표','운영계산서'])
    compact_combo(controls['회계구분'],SCOPES)
    compact_combo(controls['단위'],['전체'])
    compact_combo(controls['범위'],['수입','지출'])
    denominator_note=tk.StringVar(value='기본 분모: 교비 + 대학원 등록금수입')
    cards=ttk.Frame(body);cards.pack(fill='x',pady=(3,10));kpi_values=[]
    for i,(title,color) in enumerate([('선택 기준 금액','#E7F0FC'),('전년 대비 증감액','#6CE2C9'),('전년 대비 증감률','#70DDEA'),('선택 수입 분모 대비','#C1B5F5'),('표시 과목 구성비','#9EC4FC')]):
        cards.columnconfigure(i,weight=1,uniform='kpi')
        card=tk.Frame(cards,bg='#1D3049' if i==0 else '#1B293D',highlightbackground='#365672',highlightthickness=1,padx=12,pady=9)
        card.grid(row=0,column=i,sticky='nsew',padx=(0,7 if i<4 else 0))
        tk.Label(card,text=title,bg=card['bg'],fg='#B9CCDF',font=('맑은 고딕',9)).pack(anchor='w')
        value=tk.StringVar(value='—');kpi_values.append(value)
        tk.Label(card,textvariable=value,bg=card['bg'],fg=color,font=('맑은 고딕',17,'bold')).pack(anchor='w',pady=(4,0))
    notebook=ttk.Notebook(body);notebook.pack(fill='both',expand=True)
    analysis_tab=ttk.Frame(notebook);trend_tab=ttk.Frame(notebook)
    for tab,title in [(analysis_tab,'재무제표 구성비'),(trend_tab,'연도별 증감')]:notebook.add(tab,text=title)
    composition_view=tk.Canvas(analysis_tab,bg='#101722',highlightthickness=0);composition_view.pack(side='left',fill='both',expand=True)
    # The scene fits the viewport, so its size hint must not resize the viewport.
    composition_view._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Ignored)
    composition_scroll=ttk.Scrollbar(analysis_tab,orient='vertical',command=composition_view.yview)
    def outer_scroll(first,last):
        composition_scroll.set(first,last)
        if float(first)<=0 and float(last)>=1:composition_scroll.pack_forget()
        else:composition_scroll.pack(side='right',fill='y')
    composition_view.configure(yscrollcommand=outer_scroll)
    quadrants=ttk.Frame(composition_view);composition_id=composition_view.create_window(0,0,anchor='nw',window=quadrants)
    quadrants.rowconfigure(0,weight=1)
    trend_grid=ttk.Frame(trend_tab);trend_grid.pack(fill='both',expand=True);trend_grid.rowconfigure(0,weight=1);trend_grid.rowconfigure(1,weight=0);trend_grid.columnconfigure(0,weight=1)
    quadrants.columnconfigure(0,weight=1);quadrants.columnconfigure(1,weight=0,minsize=420)
    pie_panel=ttk.LabelFrame(quadrants,text='',padding=8,style='Dashboard.TLabelframe');pie_panel.grid(row=0,column=0,sticky='new',padx=(0,5),pady=(0,5))
    current_frame=ttk.LabelFrame(quadrants,text='',padding=8,style='Dashboard.TLabelframe');current_frame.grid(row=0,column=1,sticky='nsew',pady=(0,5))
    line_panel=ttk.LabelFrame(trend_grid,text='',padding=8,style='Dashboard.TLabelframe');line_panel.grid(row=0,column=0,sticky='nsew',padx=(0,5))
    annual_frame=ttk.Frame(body)  # 금액 표 데이터 유지; 화면에는 팝업으로만 표시
    # Keep the chart's size hint from pushing the table outside the canvas.
    for panel in (pie_panel,current_frame):
        panel._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Preferred)
    panel_fit_job=None
    applied_panel_width=None

    def schedule_panel_fit(event=None):
        nonlocal panel_fit_job
        if panel_fit_job is None:
            panel_fit_job=window.after_idle(fit_panels)

    def fit_panels():
        nonlocal panel_fit_job,applied_panel_width
        panel_fit_job=None
        width=composition_view.winfo_width()
        available=composition_view.winfo_height()
        widths=getattr(analysis_tree,'_analysis_widths',())
        table_width=sum(widths)+48 if widths else 440
        panel_width=min(max(table_width,ledgerbar.winfo_reqwidth()+24),max(1,width-6))
        if applied_panel_width!=panel_width:
            applied_panel_width=panel_width
            quadrants.columnconfigure(1,minsize=panel_width)
            current_frame.configure(width=panel_width)

        count=len(analysis_tree.get_children())
        rowheight=max(18,min(25,(available-115)//max(1,count)))
        if style.lookup('Composition.Treeview','rowheight')!=rowheight:
            style.configure('Composition.Treeview',rowheight=rowheight,background='#192738',fieldbackground='#192738',foreground='#E7EDF6')
        tree_height=max(1,count)
        if analysis_tree.cget('height')!=tree_height:
            analysis_tree.configure(height=tree_height)
        height=max(available-8,ledgerbar.winfo_reqheight()+analysis_tree.winfo_reqheight()+32)
        if current_frame.cget('height')!=height:
            current_frame.configure(height=height)
        pie_height=max(200,available-8)
        if pie_panel.cget('height')!=pie_height:
            pie_panel.configure(height=pie_height)
        canvas_height=max(available,height+8)
        scrollregion=(0,0,width,canvas_height)
        if composition_view.cget('scrollregion')!=scrollregion:
            composition_view.itemconfigure(composition_id,width=width,height=canvas_height)
            composition_view.configure(scrollregion=scrollregion)

        trend_widths=getattr(trend_tree,'_analysis_widths',())
        if trend_widths:
            room=max(0,trend_tree.winfo_width()-sum(trend_widths)-4)
            extra=room//len(trend_widths)
            for i,pixels in enumerate(trend_widths):
                column=str(i)
                if trend_tree.column(column,'width')!=pixels+extra:
                    trend_tree.column(column,width=pixels+extra)

    for panel in (composition_view,quadrants,trend_grid):
        panel.bind('<Configure>',schedule_panel_fit)
    pie_plot=ttk.Frame(pie_panel);pie_plot.pack(fill='both',expand=True)
    canvas=tk.Canvas(pie_plot,width=1,height=1,bg='#192131',highlightthickness=0);canvas.pack(side='left',fill='both',expand=True)
    pie_scroll=ttk.Scrollbar(pie_plot,orient='vertical',command=canvas.yview)
    def scroll_pie(first,last):
        pie_scroll.set(first,last)
        if float(first)<=0 and float(last)>=1:pie_scroll.pack_forget()
        else:pie_scroll.pack(side='right',fill='y')
    canvas.configure(yscrollcommand=scroll_pie)
    canvas.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-int(e.delta/120),'units'))
    ledgerbar=ttk.Frame(current_frame);ledgerbar.pack(fill='x')
    compact_headers=['과목','결산','원형 비중(%)','증감']
    analysis_tree=table(current_frame,compact_headers,auto_scroll=True);analysis_tree.configure(height=4,style='Composition.Treeview')
    series_bar=ttk.Frame(line_panel);series_bar.pack(fill='x')
    graph_type=tk.StringVar(value='꺾은선')
    trend_canvas=tk.Canvas(line_panel,width=1,height=1,bg='#192131',highlightthickness=0);trend_canvas.pack(fill='both',expand=True)
    trend_tree=table(annual_frame,['연도'],auto_scroll=True);trend_tree.configure(height=4,style='Dashboard.Treeview')

    def mark_total(tree):
        tree.tag_configure('total',background='#244C70',foreground='#FFFFFF',font=('맑은 고딕',10,'bold'))
        children=tree.get_children()
        if children:tree.item(children[-1],tags=('total',))
    def current_path():return tuple(var.get() for var in filters.values() if var.get()!='전체')
    def analysis_history():return {year:statement_view(data,statement.get()) for year,data in history.items()}
    def options(changed=None):
        if not history:return
        ranges=['자산','부채와기본금'] if statement.get()=='재무상태표' else ['수입','지출']
        if section.get() not in ranges:section.set(ranges[0])
        compact_combo(controls['범위'],ranges)
        data=statement_view(history[selected.get()],statement.get())
        units=available_units(data,scope.get())
        if unit.get() not in units:unit.set('합계')
        unit_choice.set(unit_label(unit.get()))
        compact_combo(controls['단위'],list(map(unit_label,units)) or ['전체'])
        parsed=data['datasets'].get((scope.get(),unit.get()),{})
        keys=list(filters)
        if changed in keys:
            for key in keys[keys.index(changed)+1:]:filters[key].set('전체')
        elif changed and changed!='회계연도':
            for var in filters.values():var.set('전체')
        for i,key in enumerate(keys):
            prefix=tuple(normalize(filters[k].get()) for k in keys[:i])
            candidates=[]
            for item in parsed.get('items',{}).values():
                p=item['path']
                if item['section']==section.get() and len(p)>i and tuple(map(normalize,p[:i]))==prefix and p[i] not in candidates:candidates.append(p[i])
            values=['전체']+candidates
            if filters[key].get() not in values:filters[key].set('전체')
            compact_combo(controls[key],values)
            controls[key].configure(width=min(14,int(controls[key].cget('width'))))

    graph_job=None
    def schedule_graphs(event=None):
        nonlocal graph_job
        if graph_job is not None:window.after_cancel(graph_job)
        graph_job=window.after(50,graphs)

    def graphs(event=None):
        nonlocal graph_job
        if graph_job is not None:window.after_cancel(graph_job);graph_job=None
        from analysis_charts import donut,lines,bars
        label='결산' if statement.get()=='자금계산서' else '당기'
        if selected.get() in history:
            data=statement_view(history[selected.get()],statement.get())
            _,base=analysis_rows(data,None,scope.get(),unit.get(),section.get(),current_path(),None)
            total_name=source_total_row(data,None,scope.get(),unit.get(),section.get(),statement.get())[0] if not current_path() else '선택 과목 합계'
        else:base=None;total_name='합계'
        donut(canvas,pie_values(shown),label,base,total_name)
        (bars if graph_type.get()=='막대' else lines)(trend_canvas,series_headers,series_rows,label)

    def total_path():
        kind=statement.get()
        basis='수입' if kind=='자금계산서' else '자산' if kind=='재무상태표' else section.get()
        label='자금계산서 총액' if kind=='자금계산서' else '자산총액' if kind=='재무상태표' else ('운영수익 총액' if basis=='수입' else '운영비용 총액')
        return ('__total__',basis,label)

    def update_series():
        nonlocal series_headers,series_rows
        series_headers,series_rows=multi_trend(analysis_history(),sources,scope.get(),unit.get(),section.get(),series_paths)
        total=['조회 연도 합계']+[complete_sum(r[i] for r in series_rows) for i in range(1,len(series_headers))]
        display_table(trend_tree,series_headers,series_rows+[total],range(1,len(series_headers)));mark_total(trend_tree)

    def annual_popup():
        from analysis_table_popup import amount_popup
        total=['조회 연도 합계']+[complete_sum(r[i] for r in series_rows) for i in range(1,len(series_headers))]
        amount_popup(window,series_headers,series_rows+[total],display_table,
                     f'{statement.get()} / {scope.get()} / {unit_label(unit.get())} / {section.get()}')

    def expand_selected():
        chosen=analysis_tree.selection()
        if not chosen:return
        index=analysis_tree.index(chosen[0])
        if index>=len(shown):return
        path=shown[index]['item']['path']
        if len(path)!=1:
            messagebox.showinfo('관 펼치기','전체 범위에서 관을 선택하세요.',parent=window);return
        expanded.add(path);render()
    def collapse():expanded.clear();render()
    expansionbar=ttk.Frame(ledgerbar);expansionbar.pack(side='top',fill='x')
    for value,label in ((1,'항'),(2,'목')):
        ttk.Radiobutton(expansionbar,text=label,variable=expand_depth,value=value,command=lambda:render(),style='Statement.TRadiobutton').pack(side='left')
    ttk.Button(expansionbar,text='선택 관 펼치기',command=expand_selected).pack(side='left',padx=3)
    ttk.Button(expansionbar,text='접기',command=collapse).pack(side='left',padx=3)

    def show_guan():
        if selected.get() not in history:return
        from composition_ui import open_guan_composition
        chosen=analysis_tree.selection();path=current_path()
        if chosen:
            index=analysis_tree.index(chosen[0])
            if index<len(shown):path=shown[index]['item']['path']
        open_guan_composition(window,statement_view(history[selected.get()],statement.get()),scope.get(),unit.get(),section.get(),path[0] if path else '',f'{selected.get()} · {statement.get()} · {section.get()}')
    composition_actions=ttk.Frame(pie_panel);composition_actions.pack(fill='x',before=pie_plot)
    ttk.Button(composition_actions,text='관별 구성비',command=show_guan).pack(side='left',padx=(8,3),pady=(0,4))

    def choose_series():
        if not history:return
        dialog=tk.Toplevel(window);dialog.title('연도별 비교 과목 선택')
        from ui_theme import dark_titlebar
        dark_titlebar(dialog);center(dialog,620,500)
        frame=ttk.Frame(dialog,padding=15);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='최대 6개 과목을 선택하세요. 체크박스로 여러 항목을 선택합니다.',style='Muted.TLabel').pack(anchor='w',pady=8)
        holder=ttk.Frame(frame);holder.pack(fill='both',expand=True)
        box=CheckList(holder,selectmode='extended',exportselection=False,bg='#192131',fg='#EDF2FA',selectbackground='#31546B',highlightthickness=0)
        box.pack(side='left',fill='both',expand=True);scroll=ttk.Scrollbar(holder,orient='vertical',command=box.yview);scroll.pack(side='right',fill='y');box.configure(yscrollcommand=scroll.set)
        paths=[total_path()]+[r['item']['path'] for r in shown]
        for i,path in enumerate(paths):
            box.insert('end',path[-1] if path[0]=='__total__' else ' / '.join(path))
            if path in series_paths:box.selection_set(i)
        def apply():
            nonlocal series_paths
            choices=box.curselection()
            if not 1<=len(choices)<=6:messagebox.showinfo('과목 선택','1~6개 과목을 선택하세요.',parent=dialog);return
            series_paths=[paths[i] for i in choices];update_series();graphs();dialog.destroy()
        ttk.Button(frame,text='선택 적용',command=apply).pack(anchor='e',pady=10)
    for label in ('꺾은선','막대'):
        ttk.Radiobutton(series_bar,text=label,variable=graph_type,value=label,command=graphs,style='Statement.TRadiobutton').pack(side='right',padx=5)
    canvas.bind('<Configure>',schedule_graphs);trend_canvas.bind('<Configure>',schedule_graphs)

    def render():
        nonlocal shown,trend,denom_details,checks,checked_year,check_notes,series_paths,series_context
        if selected.get() not in history:return
        from analysis_charts import compact
        current=history[selected.get()];prior_year=str(int(selected.get())-1)
        amount,denom_details,note=denominator(current,preset)
        subject_note=' + '.join(p[-1] for p in preset['paths'])
        if len(subject_note)>65:subject_note=subject_note[:62]+'…'
        denominator_note.set(f'분모(자금계산서): {preset["scope"]} / {" + ".join(map(unit_label,preset["units"]))}\n{subject_note}\n{compact(amount) if amount is not None else "자료 필요"}'+(' · 계산 제외' if note else ''))
        shown,base=expanded_composition(statement_view(current,statement.get()),statement_view(history.get(prior_year,{}),statement.get()),scope.get(),unit.get(),section.get(),current_path(),amount,expanded,expand_depth.get())
        positive=sum((r['values'][1] for r in shown if r['values'][1] is not None and r['values'][1]>0),Decimal(0))
        compact_headers[1]='결산' if statement.get()=='자금계산서' else '당기'
        compact_rows=[[r['item']['path'][-1],r['values'][1],r['values'][1]/positive*100 if positive>0 and r['values'][1] is not None and r['values'][1]>0 else None,r['values'][5]] for r in shown]
        total=analysis_total(shown,base,amount)
        from analysis_charts import compact
        from financial_analysis import ratio
        _,previous_base=analysis_rows(statement_view(history.get(prior_year,{}),statement.get()),None,scope.get(),unit.get(),section.get(),current_path(),None)
        delta=base-previous_base if base is not None and previous_base is not None else None
        growth=ratio(delta,previous_base);denom_ratio=ratio(base,amount)
        labels=[compact(base) if base is not None else '자료 필요',
                ('+' if delta>0 else '')+compact(delta) if delta is not None else '자료 필요',
                f'{growth:+,.2f}%' if growth is not None else '자료 필요',
                f'{denom_ratio:,.2f}%' if denom_ratio is not None else '자료 필요',
                f'{total[2]:,.2f}%' if total[2] is not None else '자료 필요']
        for variable,label in zip(kpi_values,labels):variable.set(label)
        source_total=source_total_row(statement_view(current,statement.get()),statement_view(history.get(prior_year,{}),statement.get()),scope.get(),unit.get(),section.get(),statement.get())
        display_table(analysis_tree,compact_headers,compact_rows+[source_total],(1,2,3))
        analysis_tree.yview_moveto(0);analysis_tree.xview_moveto(0)
        schedule_panel_fit()
        context=(statement.get(),scope.get(),unit.get(),section.get(),current_path())
        valid=[total_path()]+[r['item']['path'] for r in shown]
        if series_context!=context:series_paths=valid[:3]
        else:series_paths=[p for p in series_paths if p in valid] or valid[:3]
        series_context=context;update_series()
        for i,item in enumerate(analysis_tree.get_children()[:-1]):
            analysis_tree.tag_configure('stripe',background='#203248');analysis_tree.item(item,tags=('stripe',) if i%2 else ())
        mark_total(analysis_tree)
        trend=trend_rows(analysis_history(),scope.get(),unit.get(),section.get(),current_path(),preset,sources)
        topic_refresh()
        status.set(' / '.join(issues+current['issues']) or '원 단위 · 확정결산 · 전체는 내부거래 제거 후 금액 · 결측치는 공란')
        graphs()
    def changed(key):
        if key=='단위':unit.set('합계' if unit_choice.get()=='전체' else unit_choice.get())
        expanded.clear();options(key);render()
    for key,box in controls.items():box.bind('<<ComboboxSelected>>',lambda e,k=key:changed(k))

    def refresh():
        if jobs.busy:return
        def done(result):
            nonlocal history,issues,sources,checked_year,checks,check_notes,shown,trend,series_rows,series_headers
            history,issues,sources=result;checked_year=None;checks=[];check_notes=[]
            year_box.configure(values=list(history))
            if not history:
                shown=[];trend=[];series_rows=[];series_headers=['연도']
                for value in kpi_values:value.set('—')
                denominator_note.set('분모: 재무제표 자료 없음')
                for tree in (analysis_tree,trend_tree):tree.delete(*tree.get_children())
                canvas.delete('all');trend_canvas.delete('all');selected.set('')
                topic_refresh();status.set(' / '.join(issues) or '연도별 재무제표가 없습니다.');return
            if selected.get() not in history:selected.set(next(iter(history)))
            options();render()
        jobs.run(lambda:load_history(folder,materialize_sources=False),done)

    def ledger():
        chosen=analysis_tree.selection()
        if not chosen:return
        index=analysis_tree.index(chosen[0])
        if index>=len(shown):return
        item=shown[index]['item']
        open_ledger_details(window,desktop,center,open_file,selected.get(),scope.get(),unit.get(),item['path'])
    def export():
        if selected.get() not in history:return
        target=target_file(window,None,'재무분석')
        if not target:return
        notes=[f'회계연도 {selected.get()} / 비교연도 {int(selected.get())-1}',f'{statement.get()} / {scope.get()} / {unit_label(unit.get())} / {section.get()} / {" / ".join(current_path()) or "전체"}',
               f'원 단위 확정결산. 전체 금액은 내부거래 제거 완료. {statement.get()} 기준. 분모는 자금계산서 수입 조합.',
               '구성비=결산÷선택 부모(전체 선택 시 원본 총계). 분모 대비=결산÷선택 수입 분모. 증감=당기−직전연도. 증감률=증감÷양수 직전연도 결산.',
               '결측·0 이하 분모의 비율은 공란. 계층 중복 미합산. 과목 개편은 자동 동등 처리하지 않음.',
               '원장 거래 합계와 재무제표 결산은 이월·내부거래·결산조정 때문에 다를 수 있음.',
               *issues,*history[selected.get()]['issues'],*(check_notes if checked_year==selected.get() else ['부속명세서 대사는 재무제표 메뉴의 재무제표·부속명세서 검증에서 별도로 실행'])]
        denom,_,_=denominator(history[selected.get()],preset)
        _,base=analysis_rows(statement_view(history[selected.get()],statement.get()),None,scope.get(),unit.get(),section.get(),current_path(),denom)
        args=(target,list(shown),history[selected.get()]['basis'],list(denom_details),list(trend),list(checks),notes,base,denom,(series_headers,series_rows),statement.get(),source_total_row(statement_view(history[selected.get()],statement.get()),statement_view(history.get(str(int(selected.get())-1),{}),statement.get()),scope.get(),unit.get(),section.get(),statement.get()))
        def work():
            from analysis_runtime import statement_folder
            statement_folder()
            return export_report(*args)
        jobs.run(work,lambda p:saved(window,status,open_file,p))
    for container,title,command in [(actions,'새로고침',refresh),(actions,'Excel 저장',export),(expansionbar,'선택 과목 원장 조회',ledger),(series_bar,'비교 과목 선택',choose_series),(series_bar,'연도별 금액',annual_popup)]:
        button=ttk.Button(container,text=title,command=command);button.pack(side='left',padx=4,pady=3);jobs.controls.append(button)
    analysis_tree.bind('<Double-1>',lambda e:ledger())
    from topic_ui import install_topics
    topic_refresh=install_topics(notebook,window,jobs,lambda:(history,selected.get(),scope.get(),unit.get(),preset,current_path()),display_table,open_file)
    def tab_changed(event=None):
        if notebook.select()==str(analysis_tab):
            if not cards.winfo_manager():cards.pack(fill='x',pady=(3,10),before=notebook)
        else:cards.pack_forget()
    notebook.bind('<<NotebookTabChanged>>',tab_changed)
    window.after(100,refresh)


def open_ledger_details(parent,desktop,center,open_file,year,scope,unit,path):
    from finance_data import ledger_totals,export_ledger
    from analysis_runtime import program_ledger_paths,load_program_ledger
    window,body,status,jobs=shell(parent,f'{year} 원장 · {path[-1]}',center)
    records=[];filtered=[];page=0;size=200
    ttk.Label(body,text=f'{year} / {scope} / {unit_label(unit)} / {" → ".join(path)}',style='Accent.TLabel').pack(anchor='w')
    ttk.Label(body,text='원장 거래내역 합계입니다. 내부거래 제거·이월·결산조정에 따라 재무제표 결산과 다를 수 있습니다.',style='Muted.TLabel').pack(anchor='w',pady=5)
    bar=ttk.Frame(body);bar.pack(fill='x');query=tk.StringVar()
    ttk.Label(bar,text='거래선·적요 검색').pack(side='left');entry=ttk.Entry(bar,textvariable=query,width=30);entry.pack(side='left',padx=8);jobs.controls.append(entry)
    totals=tk.StringVar();ttk.Label(body,textvariable=totals,style='Accent.TLabel').pack(side='bottom',fill='x',pady=8)
    pager=ttk.Frame(body);pager.pack(side='bottom',fill='x');page_label=tk.StringVar();ttk.Label(pager,textvariable=page_label).pack(side='left')
    headers=['회계일자','회계단위','전표번호','거래선명','적요','차변','대변'];tree=table(body,headers)
    def show():
        count=ledger_totals(filtered)
        rows=[[r[h] for h in headers] for r in filtered[page*size:(page+1)*size]]
        rows.append(['조회 전체 합계','','','','',count['차변'],count['대변']])
        display_table(tree,headers,rows,(5,6))
        tree.tag_configure('total',background='#244C70',foreground='#FFFFFF',font=('맑은 고딕',10,'bold'))
        tree.item(tree.get_children()[-1],tags=('total',))
        tree.column('4',width=330);tree.column('0',width=95);tree.column('1',width=100)
        totals.set(f'조회 전체 합계 · {len(filtered):,}건 · 차변 {amount_text(count["차변"])}원 · 대변 {amount_text(count["대변"])}원')
        page_label.set(f'{page+1} / {max(1,(len(filtered)+size-1)//size)} 페이지')
    def search(event=None):
        nonlocal filtered,page
        q=query.get().strip().casefold();filtered=[r for r in records if not q or any(q in str(r[k]).casefold() for k in ('거래선명','적요','전표번호'))];page=0;show()
    def move(delta):
        nonlocal page
        page=max(0,min(max(0,(len(filtered)-1)//size),page+delta));show()
    def detail(event=None):
        selected=tree.selection()
        if not selected:return
        index=tree.index(selected[0])
        if index>=min(size,len(filtered)-page*size):return
        r=filtered[page*size+index]
        dialog=tk.Toplevel(window);dialog.title('거래 상세');center(dialog,700,520)
        from ui_theme import dark_titlebar
        dark_titlebar(dialog)
        text=tk.Text(dialog,bg='#192131',fg='#EDF2FA',wrap='word');text.pack(fill='both',expand=True)
        text.insert('end','\n\n'.join(f'{k}: {amount_text(v) if isinstance(v,Decimal) else v}' for k,v in r.items()));text.configure(state='disabled')
    def export():
        target=target_file(window,None,'재무분석 원장조회')
        if not target:return
        snapshot=list(filtered);jobs.run(lambda:export_ledger(snapshot,target,include_summary=False),lambda p:saved(window,status,open_file,p))
    for container,title,command in [(bar,'검색',search),(bar,'Excel 저장',export),(pager,'이전',lambda:move(-1)),(pager,'다음',lambda:move(1))]:
        b=ttk.Button(container,text=title,command=command);b.pack(side='left',padx=4);jobs.controls.append(b)
    entry.bind('<Return>',search);tree.bind('<Double-1>',detail)
    def work():
        sources=program_ledger_paths(desktop()/'settings')
        if year not in sources:raise ValueError(f'{year}년 계정별원장 자료가 없습니다.')
        return [r for r in load_program_ledger(sources[year],year) if ledger_matches(r,scope,unit,path)]
    def done(result):
        nonlocal records
        records=result;search();status.set('거래를 더블클릭하면 전체 적요와 원본 출처를 확인할 수 있습니다.')
    jobs.run(work,done)
