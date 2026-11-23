"""그래프 중심 주제별 분석. 화면 금액은 백만원, 표와 Excel은 원 단위."""
from pathlib import Path
import qt_ui as tk
from qt_ui import ttk,messagebox
from analysis_charts import lines,bars,stacked_years,grant_bars
from fund_data import load_bundled_funds,fund_series,individual_fund_series,HEADERS as FUND_HEADERS
from analysis_presentation import complete_sum
from analysis_topics import expense_history
from gov_subsidy import load_bundled_subsidies,subsidy_series
from statement_ui import table
from finance_ui import target_file,saved


def install_topics(notebook,window,jobs,context,display_table,open_file):
    states={}
    for key,title in [('ratio','수입 대비 지출'),('fund','기금사용현황'),('grants','국고보조금 현황')]:
        frame=ttk.Frame(notebook,padding=8);notebook.add(frame,text=title)
        controls=ttk.Frame(frame);controls.pack(fill='x')
        note=tk.StringVar();ttk.Label(frame,textvariable=note,style='Muted.TLabel',wraplength=1200).pack(fill='x',pady=5)
        plot=ttk.LabelFrame(frame,text=title+(' · %' if key=='ratio' else ' · 백만원'),padding=8,style='Dashboard.TLabelframe');plot.pack(fill='both',expand=True)
        canvas=tk.Canvas(plot,bg='#192131',height=160,highlightthickness=0);canvas.pack(fill='both',expand=True)
        table_frame=ttk.LabelFrame(frame,text='상세 내역 · 원',padding=5,style='Dashboard.TLabelframe');
        tree=table(table_frame,['회계연도']);tree.configure(height=5,style='Dashboard.Treeview')
        state={'frame':frame,'note':note,'canvas':canvas,'tree':tree,'headers':[], 'rows':[], 'plot_headers':[], 'plot_rows':[], 'sources':[], 'ratios':[],'subsidies':{},'source_notes':[],'counts':{},'funds':{}}
        states[key]=state
        export_button=ttk.Button(controls,text='Excel 저장',command=lambda k=key:export(k));export_button.pack(side='right');jobs.controls.append(export_button)
        mode=tk.StringVar(value={'ratio':'자금계산서 총액','fund':'임의기금 잔액','grants':''}[key]);state['mode']=mode
        if key in ('ratio','fund','grants'):
            button=ttk.Button(controls,text='연도별 금액',command=lambda k=key:annual_popup(k));button.pack(side='left',padx=5);jobs.controls.append(button)
        ttk.Label(controls,text='연도 범위').pack(side='left',padx=(12,4))
        span=tk.StringVar(value='5개년');box=ttk.Combobox(controls,textvariable=span,values=['5개년','10개년','전체'],state='readonly',width=8);box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda e:refresh());state['span']=span
        if key in ('grants','fund'):
            ttk.Label(controls,text='기준연도').pack(side='left',padx=(12,3))
            year=tk.StringVar();box=ttk.Combobox(controls,textvariable=year,state='readonly',width=7);box.pack(side='left');box.bind('<<ComboboxSelected>>',lambda e,k=key:render_grants() if k=='grants' else render_funds())
            state.update(year=year,year_box=box)
        if key=='fund':
            state['individual']=None
            ttk.Button(controls,text='개별 기금 선택',command=lambda:choose_funds()).pack(side='left',padx=5)
            graph=tk.StringVar(value='꺾은선');state['graph']=graph
            for label in ('꺾은선','막대'):
                ttk.Radiobutton(controls,text=label,variable=graph,value=label,command=lambda:draw('fund'),style='Statement.TRadiobutton').pack(side='left',padx=4)
            ttk.Button(controls,text='기금 상세 내역',command=lambda:fund_details()).pack(side='left',padx=5)
        canvas.bind('<Configure>',lambda e,k=key:draw(k))

    def annual_popup(key):
        from analysis_table_popup import amount_popup
        s=states[key];headers=s['headers'];rows=s['rows']
        total=['조회 연도 합계',*[complete_sum(row[i] for row in rows) for i in range(1,len(headers))]]
        amount_popup(window,headers,rows+[total],display_table,s['mode'].get() if key=='ratio' else '기말잔액 · 원' if key=='fund' else '국고보조금 · 원')

    def draw(key):
        s=states[key]
        if key=='ratio':stacked_years(s['canvas'],s['plot_headers'],s['ratios'],s['rows'])
        elif key=='fund':(bars if s['graph'].get()=='막대' else lines)(s['canvas'],s['plot_headers'],s['plot_rows'],'기말잔액')
        elif key=='grants':grant_bars(s['canvas'],s['plot_headers'],s['plot_rows'],s['counts'])

    def show(key):
        s=states[key];headers=s['headers'];rows=s['rows']
        values=rows+[['조회 연도 합계',*[complete_sum(row[i] for row in rows) for i in range(1,len(headers))]]]
        display_table(s['tree'],headers,values,range(1,len(headers)))
        s['tree'].tag_configure('total',background='#244C70',foreground='#FFFFFF',font=('맑은 고딕',9,'bold'))
        s['tree'].tag_configure('attention',background='#54472B',foreground='#FFE5A3')
        children=s['tree'].get_children()
        for iid,row in zip(children,values):
            if row[0] in ('합계','조회 연도 합계'):s['tree'].item(iid,tags=('total',))
        draw(key)

    def subset(history,year,state):
        span=state['span'].get();lower=int(year)-(4 if span=='5개년' else 9) if span!='전체' else 0
        return {y:v for y,v in history.items() if lower<=int(y)<=int(year)}

    def refresh():
        history,year,scope,unit,preset,path=context()
        for key in ('ratio',):
            s=states[key]
            if not history or year not in history:
                s.update(headers=['회계연도'],rows=[],plot_headers=['회계연도'],plot_rows=[],ratios=[],sources=[]);s['note'].set('재무제표 자료 없음');show(key);continue
            selected=subset(history,year,s);s['sources']=[str(d['source']) for d in selected.values()]
            if key=='ratio':
                basis='총액' if s['mode'].get()=='자금계산서 총액' else '선택'
                s['headers'],s['rows'],s['ratios'],notes=expense_history(selected,preset,scope,unit,basis)
                s['plot_headers']=s['headers'][:-1];s['plot_rows']=s['rows']
                s['note'].set(f'{scope} / {"전체" if unit=="합계" else unit} · 연도별 {s["mode"].get()} = 100% · 초과 비율 유지 · 누락/음수 연도는 표 확인'+(' · '+' / '.join(notes) if notes else ''))
            show(key)
        render_grants();render_funds()

    def render_grants():
        s=states['grants'];history=s['subsidies'];year=s['year'].get()
        selected=subset(history,year,s) if history and year else {}
        headers,rows=subsidy_series(selected)
        if rows:
            indexed={int(r[0]):r for r in rows}
            rows=[indexed.get(y,[str(y),*[None]*(len(headers)-1)]) for y in range(min(indexed),max(indexed)+1)]
        s['plot_headers']=headers;s['plot_rows']=rows;s['counts']={y:d['count'] for y,d in selected.items()}
        s['headers']=[*headers,'합계','사업 건수'];s['rows']=[r+[complete_sum(r[1:]),s['counts'].get(r[0])] for r in rows]
        s['sources']=[str(d['source']) for d in selected.values()]
        s['note'].set('내장 국고보조금명세서 결산액 · 전체 회계단위 · 막대: 계정과목별(좌측) / 선: 합계(우측)'+(' · '+' / '.join(s['source_notes']) if s['source_notes'] else ''))
        show('grants')

    def load_grants():
        if not window.winfo_exists():return
        if jobs.busy:
            window.after(250,load_grants);return
        def done(result):
            s=states['grants'];s['subsidies'],s['source_notes']=result
            years=sorted(s['subsidies'],reverse=True);s['year_box'].configure(values=years)
            if s['year'].get() not in years:s['year'].set(years[0] if years else '')
            render_grants()
        jobs.run(load_bundled_subsidies,done)

    def render_funds():
        s=states['fund'];history=s['funds'];year=s['year'].get()
        selected=subset(history,year,s) if history and year else {}
        headers,rows=individual_fund_series(selected,s['individual']) if s['individual'] is not None else fund_series(selected)
        s['plot_headers']=headers;s['plot_rows']=rows
        s['headers']=[*headers,'합계'];s['rows']=[r+[complete_sum(r[1:])] for r in rows]
        s['sources']=[str(d['source']) for d in selected.values()]
        s['note'].set('내장 기금 자료 · 기말잔액 · 선택 기금/구분별 비교 (상단 재무제표 회계구분과 별도)'+(' · '+' / '.join(s['source_notes']) if s['source_notes'] else ''))
        show('fund')

    def choose_funds():
        from check_list import CheckList
        s=states['fund'];choices=sorted({(r[0],r[1]) for data in s['funds'].values() for r in data['details']})
        if not choices:
            messagebox.showinfo('개별 기금','기금 자료를 먼저 불러오세요.',parent=window);return
        dialog=tk.Toplevel(window);dialog.title('비교할 개별 기금 선택');dialog.geometry('640x480')
        frame=ttk.Frame(dialog);frame.pack(fill='both',expand=True,padx=12,pady=12)
        box=CheckList(frame,selectmode='extended',exportselection=False,width=65)
        box.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=box.yview);scroll.pack(side='right',fill='y');box.configure(yscrollcommand=scroll.set)
        for i,key in enumerate(choices):
            box.insert('end',' / '.join(key))
            if s['individual'] is not None and key in s['individual']:box.selection_set(i)
        def apply(grouped=False):
            selected=[choices[i] for i in box.curselection()]
            if not grouped and not selected:return
            s['individual']=None if grouped else selected
            render_funds();dialog.destroy()
        ttk.Button(dialog,text='선택 기금 비교',command=apply).pack(side='right',padx=12,pady=12)
        ttk.Button(dialog,text='구분별 전체로 복귀',command=lambda:apply(True)).pack(side='left',padx=12,pady=12)

    def load_fund_data():
        if not window.winfo_exists():return
        if jobs.busy:window.after(250,load_fund_data);return
        def done(result):
            s=states['fund'];s['funds'],s['source_notes']=result
            years=sorted(s['funds'],reverse=True);s['year_box'].configure(values=years)
            if s['year'].get() not in years:s['year'].set(years[0] if years else '')
            render_funds()
        jobs.run(load_bundled_funds,done)

    def fund_details():
        from analysis_table_popup import amount_popup
        s=states['fund'];data=s['funds'].get(s['year'].get())
        if not data:messagebox.showinfo('기금 상세 내역','먼저 기금 자료를 불러오세요.',parent=window);return
        rows=data['details'];total=['합계','',*[complete_sum(r[i] for r in rows) for i in range(2,6)]]
        amount_popup(window,FUND_HEADERS,rows+[total],display_table,s['year'].get()+'년 기금 상세 · 원')

    def export(key):
        s=states[key]
        if not s['rows']:messagebox.showinfo('저장','먼저 자료를 불러오세요.',parent=window);return
        path=target_file(window,None,{'ratio':'수입 대비 지출','fund':'기금사용현황','grants':'국고보조금 현황'}[key])
        if not path:return
        headers=list(s['headers']);rows=[list(r) for r in s['rows']];note=s['note'].get();sources=list(s['sources'])
        fund_bars=key=='fund' and s['graph'].get()=='막대'
        fund_details_snapshot={r[0]:[list(v) for v in s['funds'][r[0]]['details']] for r in rows if r[0] in s['funds']} if key=='fund' else {}
        ph=list(s['plot_headers']);pr=[list(r) for r in (s['ratios'] if key=='ratio' else s['plot_rows'])]
        if key=='grants':
            ph=[*ph,'합계'];pr=[r+[complete_sum(r[1:])] for r in pr]
        def work():
            if key=='ratio':
                from analysis_runtime import statement_folder
                for source in sources:
                    statement_folder(Path(source).name[:4])
            from openpyxl import Workbook
            from finance_data import append_row,format_sheet,save_atomic
            from openpyxl.chart import LineChart,BarChart,Reference
            from openpyxl.chart.label import DataLabelList
            wb=Workbook();ws=wb.active;ws.title='분석';append_row(ws,headers)
            for row in rows:append_row(ws,row)
            append_row(ws,['조회 연도 합계',*[complete_sum(r[i] for r in rows) for i in range(1,len(headers))]])
            format_sheet(ws)
            criteria=wb.create_sheet('분석 기준');append_row(criteria,['기준',note])
            for source in sources:append_row(criteria,['원본',source])
            format_sheet(criteria)
            for year,details in fund_details_snapshot.items():
                detail=wb.create_sheet(year+'년 기금 상세');append_row(detail,FUND_HEADERS)
                for row in details:append_row(detail,row)
                append_row(detail,['합계','',*[complete_sum(r[i] for r in details) for i in range(2,6)]])
                format_sheet(detail)
            chartdata=wb.create_sheet('그래프 데이터');append_row(chartdata,ph)
            for row in pr:append_row(chartdata,row)
            format_sheet(chartdata)
            if pr and len(ph)>1:
                chart=BarChart() if key in ('ratio','grants') or fund_bars else LineChart()
                if key=='ratio':chart.grouping='stacked';chart.overlap=100;chart.y_axis.title='수입 분모 대비 (%)'
                chart.title={'ratio':'수입 대비 지출','fund':'기금 현황','grants':'국고보조금'}[key]
                chart.add_data(Reference(chartdata,min_col=2,max_col=len(ph)-(1 if key=='grants' else 0),min_row=1,max_row=len(pr)+1),titles_from_data=True)
                chart.set_categories(Reference(chartdata,min_col=1,min_row=2,max_row=len(pr)+1))
                chart.dataLabels=DataLabelList();chart.dataLabels.showVal=True
                if key!='ratio':
                    chart.y_axis.numFmt='#,##0,,';chart.y_axis.title='백만원';chart.dataLabels.numFmt='#,##0,,'
                if key=='grants':chart.y_axis.scaling.min=0;chart.y_axis.majorUnit=5000000000
                if key=='grants':
                    total_line=LineChart();total_line.y_axis.axId=200;total_line.y_axis.crosses='max';total_line.y_axis.title='합계 (백만원)';total_line.y_axis.numFmt='#,##0,,'
                    total_line.add_data(Reference(chartdata,min_col=len(ph),max_col=len(ph),min_row=1,max_row=len(pr)+1),titles_from_data=True)
                    total_line.set_categories(Reference(chartdata,min_col=1,min_row=2,max_row=len(pr)+1))
                    total_line.y_axis.scaling.min=0;total_line.y_axis.majorUnit=5000000000
                    total_line.dataLabels=DataLabelList();total_line.dataLabels.showVal=True;total_line.dataLabels.numFmt='#,##0,,'
                    chart+=total_line
                chartdata.add_chart(chart,'J2')
            return save_atomic(wb,path)
        jobs.run(work,lambda p:saved(window,tk.StringVar(),open_file,p))
    window.after(250,load_grants)
    window.after(300,load_fund_data)
    return refresh
