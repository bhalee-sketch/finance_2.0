"""Automatic reserve sources and independently reported statutory limit checks."""
from numeric_tree import NumericTreeview
import qt_ui as tk
from qt_ui import ttk,messagebox
from statement_catalog import discover_years,amount_text
from reserve_review import calculate
from analysis_runtime import load_program_reserves as load_reserves
from finance_data import money


def fit_review_rows(tree,*,fixed=False):
    view=tree._q
    header=view.horizontalHeader()
    height=(view.verticalHeader().length()+max(header.height(),header.sizeHint().height())
            +view.horizontalScrollBar().sizeHint().height()+2*view.frameWidth())
    if fixed and (view.minimumHeight()!=height or view.maximumHeight()!=height):
        view.setFixedHeight(height)
    elif view.minimumHeight()!=height:
        view.setMinimumHeight(height)


def build_reserve_tab(body,window,desktop,jobs,status,external=False):
    year=tk.StringVar();venture=tk.StringVar();paths={};data=None
    bar=ttk.Frame(body);bar.pack(fill='x',pady=(0,8))
    ttk.Label(bar,text='회계연도').pack(side='left') if not external else None
    years=ttk.Combobox(bar,textvariable=year,state='readonly',width=8);years.pack(side='left',padx=8) if not external else None;jobs.controls.append(years)
    ttk.Label(bar,text='벤처기업 투자액(원, 확인 후 입력)').pack(side='left',padx=(12,6))
    entry=ttk.Entry(bar,textvariable=venture,width=18);entry.pack(side='left');jobs.controls.append(entry)
    ttk.Label(body,text='② 원장 등록금회계전입금 대변 합계 · ③ 임의건축적립금 당기액−⑥ · ⑤ 임의적립금 당기액\n⑥ 건축기금(감가상각) 기말잔액 · ⑦ 투자한도 기준=⑤−⑥ · ⑨ 부속명세서 투자원금 합계',style='Muted.TLabel',wraplength=1050).pack(fill='x',pady=(0,10))
    columns=('label','amount','basis')
    tree=NumericTreeview(body,columns=columns,show='headings',height=10)
    for key,title,width in [('label','검토 항목',310),('amount','금액 / 결과',200),('basis','산식·자료 기준',510)]:
        tree.heading(key,text=title);tree.column(key,width=width,minwidth=100,anchor='e' if key=='amount' else 'w')
    tree.pack(fill='both',expand=True)
    if external:
        tree.bind('<Configure>',lambda event:fit_review_rows(tree),add='+')
    result_text=tk.StringVar(value='자료를 불러오세요.')
    ttk.Label(body,textvariable=result_text,style='Accent.TLabel',wraplength=1050).pack(fill='x',pady=8)
    ttk.Label(body,text='기준: 사용자 제공 「사립학교법」 제32조의2 제3항 · 등록금 재원 제외 적립금의 증권 50%, 벤처 10% 한도\n③은 요청하신 기말금액 차감 산식이며 당기 순증가액이 아닙니다. 벤처 입력 공란은 0원이 아닌 미확인입니다.',style='Muted.TLabel',wraplength=1050).pack(fill='x')
    def draw():
        if data is None:return
        try:v=money(venture.get()) if venture.get().strip() else None
        except ValueError as exc:messagebox.showerror('벤처 투자액',str(exc),parent=window);return
        if v is not None and v<0:messagebox.showerror('벤처 투자액','0원 이상 입력하세요.',parent=window);return
        values=data['values'];r=calculate(values,values.get('securities'),v);tree.delete(*tree.get_children())
        def row(label,amount,basis):tree.insert('','end',values=(label,'—' if amount is None else amount_text(amount)+'원',basis))
        for label,key in [('① 당기 건물감가상각비','depreciation'),('② 당기 등록금회계 전출액','transfer')]:row(label,values.get(key),data['sources'].get(key,''))
        row('③ 비등록금 재원 건축적립금',r['other_building'],'임의건축적립금 당기액 − ⑥')
        tree.insert('','end',values=('④ 감가상각비 범위 내 전출',r['capital_state'],'② ≤ ①'))
        row('⑤ 누적 적립금 총계',values.get('reserve_total'),'재무상태표(전체) · 임의적립금(항) · 당기')
        row('⑥ 등록금 재원 건축적립금',values.get('tuition_reserve'),'임의건축기금 / 건축기금(감가상각) · 기말잔액')
        row('⑦ 비등록금 재원 적립금',r['base'],'⑤ − ⑥')
        row('⑨ 증권투자금액',values.get('securities'),'적립기금 유가증권 투자 명세서 · 투자원금 합계')
        row('⑩ 벤처기업 투자금액',v,'직접 확인·입력 (연도 변경 시 초기화)')
        row('증권투자 한도',r['securities']['limit'],'⑦ × 50%')
        row('벤처기업 투자 한도',r['venture']['limit'],'⑦ × 10%')
        if external:fit_review_rows(tree)
        def label(key):
            item=r[key];ratio='비율 미산출' if item['ratio'] is None else f"{item['ratio']:.4f}%"
            return f"{item['state']} ({ratio})"
        result_text.set('증권: '+label('securities')+'  /  벤처기업: '+label('venture'))
        notes=list(data['issues'])
        if r['base'] is not None and r['base']<0:notes.append('등록금 재원 적립금이 전체 적립금보다 큽니다.')
        if r['other_building'] is not None and r['other_building']<0:notes.append('건축기금(감가상각)이 임의건축적립금보다 큽니다.')
        status.set(' / '.join(notes) or '자동 자료 연결 완료 · 벤처기업 투자액은 별도 확인하세요.')
    button=ttk.Button(bar,text='검증',command=draw);button.pack(side='left',padx=8);jobs.controls.append(button)
    def load(event=None):
        nonlocal data
        if jobs.busy:return
        data=None;venture.set('');tree.delete(*tree.get_children());result_text.set('자료 확인 필요')
        path=paths.get(year.get())
        if path is None:status.set('선택연도 재무제표가 없습니다.');return
        def done(result):
            nonlocal data
            data=result;draw()
        selected=year.get();jobs.run(lambda:load_reserves(desktop()/'settings',selected,path),done)
    def refresh():
        nonlocal paths
        if jobs.busy:return
        try:paths=discover_years(desktop()/'settings'/'finance statement')
        except ValueError as exc:status.set(str(exc));return
        years.configure(values=list(paths))
        if year.get() not in paths:year.set(next(iter(paths),''))
        load()
    def render(result):
        nonlocal data
        data=result;venture.set('');tree.delete(*tree.get_children());result_text.set('자료 확인 필요')
        if data is not None:draw()
    if external:return render
    refresh_button=ttk.Button(bar,text='자료 불러오기 / 새로고침',command=refresh);refresh_button.pack(side='right');jobs.controls.append(refresh_button)
    years.bind('<<ComboboxSelected>>',load)
