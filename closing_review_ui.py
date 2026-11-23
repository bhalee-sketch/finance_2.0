"""Compact closing-review view: only year, carryover breakdown and ratio."""
from numeric_tree import NumericTreeview
import qt_ui as tk
from qt_ui import ttk,messagebox
from statement_ui import Jobs
from statement_catalog import amount_text
from analysis_runtime import program_statement_paths,statement_folder
from statement_loader import load_statement_record_from_path
from closing_review import review_carryover,review_fund_transfers
from ui_theme import dark_titlebar
from reserve_review import calculate
from analysis_runtime import load_program_reserves as load_reserves
from closing_dashboard import ClosingDashboard


def open_closing_review(parent,desktop,center):
    window=tk.Toplevel(parent);window.title('결산검토');dark_titlebar(window);center(window,1160,740)
    body=ttk.Frame(window,padding=16);body.pack(fill='both',expand=True)
    status=tk.StringVar();jobs=Jobs(window,status);year=tk.StringVar();paths={}
    bar=ttk.Frame(body);bar.pack(fill='x',pady=(0,8))
    tabs=ttk.Notebook(body);tabs.pack(fill='both',expand=True)
    summary_frame=ttk.Frame(tabs,padding=10);tabs.add(summary_frame,text='결산검토 대시보드')
    summary=ClosingDashboard(summary_frame);summary.pack(fill='both',expand=True)
    def detail_tab(title):
        frame=ttk.Frame(tabs,padding=8)
        tabs.add(frame,text=title)
        return frame
    carry_body=detail_tab('재무제표 점검')
    reserve_body=detail_tab('적립금 투자 검토')
    ttk.Label(body,textvariable=status,wraplength=1000,style='Muted.TLabel').pack(fill='x')
    from reserve_review_ui import build_reserve_tab,fit_review_rows
    render_reserves=build_reserve_tab(reserve_body,window,desktop,jobs,status,external=True)
    body=carry_body
    bar_layout=tk.W.QHBoxLayout(bar._q)
    bar_layout.setContentsMargins(0,0,0,0)
    bar_layout.setSpacing(8)
    center_vertical=tk.C.Qt.AlignmentFlag.AlignVCenter
    def add_control(widget):
        bar_layout.addWidget(widget._q,0,center_vertical)
        widget._q.show()

    add_control(ttk.Label(bar,text='회계연도'))
    box=ttk.Combobox(bar,textvariable=year,state='readonly',width=8)
    add_control(box);jobs.controls.append(box)
    button=ttk.Button(bar,text='새로고침',command=lambda:refresh())
    add_control(button);jobs.controls.append(button)
    bar_layout.addStretch()
    add_control(ttk.Label(bar,text='이월금: 등록금회계 / 임의기금 대사: 전체  ·  단위: 원',style='Muted.TLabel'))
    ttk.Label(body,text='이월금 검토',style='Section.TLabel').pack(anchor='w',pady=(0,10))
    content=ttk.Frame(body);content.pack(fill='both',expand=True)
    left=ttk.Frame(content);left.pack(side='left',fill='both',expand=True,padx=(0,16))
    tree=NumericTreeview(left,columns=('group','name','amount'),show='headings',height=8)
    for key,label,width in [('group','구분',125),('name','내역',190),('amount','금액',165)]:
        tree.heading(key,text=label);tree.column(key,width=width,minwidth=90,anchor='e' if key=='amount' else 'w')
    tree.pack(fill='both',expand=True)
    tree.bind('<Configure>',lambda event:fit_review_rows(tree),add='+')
    right=ttk.Frame(content);right.pack(side='right',fill='both',expand=True)
    values={}
    for label,key in [('자금계산서 수입','income'),('사고이월 가정액 (기말 선급금)','advance'),('기타이월금','other'),('기타이월금 비율','ratio'),('1.0% 기준금액','limit')]:
        row=ttk.Frame(right);row.pack(fill='x',pady=7)
        ttk.Label(row,text=label).pack(side='left');values[key]=tk.StringVar(value='—')
        ttk.Label(row,textvariable=values[key],style='Accent.TLabel').pack(side='right',padx=(12,0))
    verdict=tk.StringVar(value='자료 확인 중')
    ttk.Label(right,textvariable=verdict,style='Section.TLabel').pack(anchor='e',pady=12)
    ttk.Label(body,text='간이 검토: 기타이월금 = 미사용 차기이월자금 − 기말 선급금(전액 사고이월 가정)\n비율 = 기타이월금 ÷ 자금계산서 수입총액 × 100 · 실제 이월 유형의 적정성을 확정하는 판정은 아닙니다.',style='Muted.TLabel',wraplength=1000).pack(fill='x',pady=(12,4))
    ttk.Label(body,text='임의기금 · 운영계산서 대사 (전체)',style='Section.TLabel').pack(anchor='w',pady=(8,4))
    comparison=NumericTreeview(body,columns=('source','a','target','b','diff','state'),show='headings',height=2)
    for key,label,width in [('source','자금계산서',180),('a','결산액',170),('target','운영계산서',160),('b','당기액',170),('diff','차이 (자금−운영)',170),('state','결과',120)]:
        comparison.heading(key,text=label);comparison.column(key,width=width,minwidth=80,anchor='e' if key in ('a','b','diff') else 'w')
    comparison.pack(fill='x',pady=(0,5))
    comparison.bind('<Configure>',lambda event:fit_review_rows(comparison,fixed=True),add='+')
    def clear():
        tree.delete(*tree.get_children());comparison.delete(*comparison.get_children())
        summary.clear();render_reserves(None)
        for var in values.values():var.set('—')
        verdict.set('자료 확인 필요')
    def load(event=None):
        if jobs.busy:return
        clear();path=paths.get(year.get())
        if path is None:status.set('settings/finance statement에 연도별 재무제표가 없습니다.');return
        def done(payload):
            result,comparisons,reserves,errors=payload
            render_reserves(reserves)
            rv=reserves['values'] if reserves else {}
            calculated=calculate(rv,rv.get('securities'))
            summary.set_results(year.get(),result,comparisons,rv,calculated)
            for item in comparisons:
                comparison.insert('','end',values=(item['section']+' 임의기금',amount_text(item['source']) if item['source'] is not None else '—',item['target'],amount_text(item['amount']) if item['amount'] is not None else '—',amount_text(item['difference']) if item['difference'] is not None else '—',item['state']))
            for group,name,amount in result['details']:tree.insert('','end',values=(group,name,amount_text(amount) if amount is not None else '—'))
            tree.insert('','end',values=('미사용 차기이월자금','유동자산 − 유동부채',amount_text(result['carryover']) if result['carryover'] is not None else '—'))
            fit_review_rows(tree);fit_review_rows(comparison,fixed=True)
            for key,var in values.items():
                value=result[key];var.set('—' if value is None else (f'{value:.4f}%' if key=='ratio' else amount_text(value)+'원'))
            verdict.set(result['state'])
            notes=errors+result['issues']+[note for item in comparisons for note in item['notes']]+(reserves['issues'] if reserves else [])
            status.set(' / '.join(notes) or f"이월금 자료 대사 일치 · 임의기금: 수입 {comparisons[0]['state']}, 지출 {comparisons[1]['state']} · 원본: {path.name}")
        selected=year.get();settings=desktop()/'settings'
        def work():
            statement_folder(selected)
            record=load_statement_record_from_path(path)
            errors=[]
            try:carry=review_carryover(record)
            except Exception as exc:
                errors.append(str(exc));carry=dict.fromkeys(('carryover','advance','income','other','ratio','limit'))
                carry.update(details=[],state='자료 확인 필요',issues=[])
            comparisons=review_fund_transfers(record)
            try:reserves=load_reserves(settings,selected,path,statement_record=record)
            except Exception as exc:errors.append(str(exc));reserves=None
            return carry,comparisons,reserves,errors
        jobs.run(work,done)
    def refresh():
        if jobs.busy:return
        def done(result):
            nonlocal paths
            paths=result;box.configure(values=list(paths))
            if year.get() not in paths:year.set(next(iter(paths),''))
            load()
        jobs.run(lambda:program_statement_paths(materialize=False),done)
    box.bind('<<ComboboxSelected>>',load);window.after(100,refresh)
