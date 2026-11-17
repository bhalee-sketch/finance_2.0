"""Income-account review tab, with paging and original-row evidence."""
from numeric_tree import NumericTreeview
import qt_ui as tk
from qt_ui import ttk,messagebox
from finance_data import discover_ledger_years,load_ledger
from statement_catalog import amount_text
from income_scope_review import review_income
from ui_theme import dark_titlebar


def build_income_tab(body,window,desktop,jobs,status):
    year=tk.StringVar();kind=tk.StringVar(value='전체');paths={};items=[];shown=[];page=0
    bar=ttk.Frame(body);bar.pack(fill='x',pady=(0,10))
    ttk.Label(bar,text='원장 회계연도').pack(side='left')
    years=ttk.Combobox(bar,textvariable=year,state='readonly',width=8);years.pack(side='left',padx=8);jobs.controls.append(years)
    types=ttk.Combobox(bar,textvariable=kind,state='readonly',width=16,values=['전체','분류 의심','예외 확인','정정·반환 확인','회계단위 확인']);types.pack(side='left',padx=8);jobs.controls.append(types)
    summary=tk.StringVar(value='원장을 불러와 검토하세요.')
    ttk.Label(body,textvariable=summary,style='Accent.TLabel').pack(anchor='w',pady=(0,6))
    ttk.Label(body,text='등록금수입 ↔ 회계단위 교차 점검 · 잡수입/고정자산 매각은 예외 확인 · 정정·반환은 원거래 확인\n적요만으로 수입을 추정하지 않습니다. 일치 거래는 숨기며 예외의 적정성을 확정하지 않습니다.',style='Muted.TLabel').pack(anchor='w',pady=(0,8))
    panel=ttk.Frame(body);panel.pack(fill='both',expand=True)
    columns=('state','unit','date','account','debit','credit','description')
    tree=NumericTreeview(panel,columns=columns,show='headings',height=8)
    for key,title,width in zip(columns,['검토 결과','회계단위','회계일자','계정과목','차변','대변','적요'],[120,110,95,140,120,120,260]):
        tree.heading(key,text=title);tree.column(key,width=width,minwidth=65,anchor='e' if key in ('debit','credit') else 'w')
    sy=ttk.Scrollbar(panel,orient='vertical',command=tree.yview);sx=ttk.Scrollbar(panel,orient='horizontal',command=tree.xview)
    tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set);sy.pack(side='right',fill='y');sx.pack(side='bottom',fill='x');tree.pack(fill='both',expand=True)
    footer=ttk.Frame(body);footer.pack(fill='x',pady=6);pager=tk.StringVar()
    ttk.Label(footer,textvariable=pager).pack(side='left')
    def draw():
        tree.delete(*tree.get_children())
        for item in shown[page*200:(page+1)*200]:
            r=item['record'];tree.insert('','end',values=[item['state'],r['회계단위'],r['회계일자'],r['목'],amount_text(r['차변']),amount_text(r['대변']),r['적요']])
        pager.set(f'{page+1}/{max(1,(len(shown)+199)//200)}쪽 · {len(shown):,}건 · 더블클릭: 사유·원본 위치')
    def filter_items(event=None):
        nonlocal shown,page
        shown=[i for i in items if kind.get()=='전체' or i['state']==kind.get()];page=0;draw()
    def move(delta):
        nonlocal page
        page=max(0,min(max(0,(len(shown)-1)//200),page+delta));draw()
    for title,delta in [('다음',1),('이전',-1)]:ttk.Button(footer,text=title,command=lambda d=delta:move(d)).pack(side='right',padx=4)
    def detail(event=None):
        if not tree.selection():return
        item=shown[page*200+tree.index(tree.selection()[0])];r=item['record']
        dialog=tk.Toplevel(window);dialog.title('수입 회계구분 검토 · 상세');dark_titlebar(dialog)
        text=tk.Text(dialog,wrap='word',width=85,height=23);text.pack(fill='both',expand=True)
        text.insert('1.0',f"{item['state']}\n원칙상 회계: {item['expected']}\n\n{item['reason']}\n\n"+'\n'.join(f'{k}: {r[k]}' for k in ('회계단위','관','항','목','회계일자','전표번호','차변','대변','거래선명','적요'))+f"\n\n원본: {r.get('_source_file','')}\n행: {r.get('_source_row','')}\n기준: 사용자 제공 결산 제출 유의사항의 교비회계 수입인식 구분")
        text.configure(state='disabled')
    tree.bind('<Double-1>',detail);types.bind('<<ComboboxSelected>>',filter_items)
    def load(event=None):
        nonlocal items
        if jobs.busy:return
        items=[];filter_items();summary.set('자료 확인 중…');path=paths.get(year.get())
        if path is None:summary.set('해당 연도의 원장 파일이 없습니다.');return
        def done(result):
            nonlocal items
            items=result['items'];c=result['counts'];filter_items()
            summary.set(f"전체 {result['total']:,}건 · 수입 거래 {c['수입 거래']:,}건 · 분류 의심 {c['분류 의심']:,}건 · 예외 확인 {c['예외 확인']:,}건 · 정정/반환 {c['정정·반환 확인']:,}건 · 회계단위 확인 {c['회계단위 확인']:,}건")
            status.set(f'수입 회계구분 검토 완료 · 원본: {path.name} · 등록된 수입 과목 및 관·항 기준, 미등록 계층은 검사 범위 밖입니다.')
        jobs.run(lambda:review_income(load_ledger(path,with_provenance=True)),done)
    def refresh():
        nonlocal paths
        if jobs.busy:return
        try:paths=discover_ledger_years(desktop()/'settings'/'lodges')
        except ValueError as exc:status.set(str(exc));return
        years.configure(values=list(paths))
        if year.get() not in paths:year.set(next(iter(paths),''))
        load()
    button=ttk.Button(bar,text='원장 불러오기 / 새로고침',command=refresh);button.pack(side='left',padx=8);jobs.controls.append(button)
    years.bind('<<ComboboxSelected>>',load)
    draw()
