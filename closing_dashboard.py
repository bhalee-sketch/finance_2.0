"""One-screen closing dashboard using existing review calculations only."""
from qt_ui import ttk
from statement_catalog import amount_text
from appearance import NumericFont

GOOD=('일치','1.0% 이내','한도 이내')
BAD=('불일치','1.0% 초과','한도 초과')


def dashboard_rows(payload):
    if not payload:return [(name,'자료 확인 필요','—','—') for name in ('등록금 이월','기금 수입 대체','기금 지출 대체','감가상각비 내 전출','증권투자 한도')]
    year,carry,comparisons,reserves,result=payload
    money=lambda v:'—' if v is None else amount_text(v)+'원'
    ratio=carry.get('ratio')
    rows=[('등록금 이월',carry['state'],'비율 '+('—' if ratio is None else f'{ratio:.4f}%')+' / 기준 1% 이하 ('+money(carry.get('limit'))+')','기타이월금 '+money(carry.get('other'))+' / 등록금 수입 '+money(carry.get('income')))]
    for item in comparisons:
        rows.append(('기금 '+item['section']+' 대체',item['state'],'차이 '+money(item['difference']),'임의기금 '+money(item['source'])+' / '+item['target']+' '+money(item['amount'])))
    rows.append(('감가상각비 내 전출',result['capital_state'],'전출 '+money(reserves.get('transfer')),'건물감가상각비 한도 '+money(reserves.get('depreciation'))))
    rows.append(('증권투자 한도',result['securities']['state'],'투자원금 '+money(reserves.get('securities')),'비등록금 재원 적립금의 50% 한도 '+money(result['securities']['limit'])))
    return rows


class ClosingDashboard(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent);self.payload=None
        self.render()
    def clear(self):
        if self.payload is not None:
            self.payload=None;self.render()
    def set_results(self,year,carry,comparisons,reserves,calculated):
        self.payload=year,carry,comparisons,reserves,calculated;self.render()
    def render(self):
        for child in self.winfo_children():child.destroy()
        rows=dashboard_rows(self.payload)
        passed=sum(r[1] in GOOD for r in rows);failed=sum(r[1] in BAD for r in rows);unknown=len(rows)-passed-failed
        money=lambda value:'—' if value is None else amount_text(value)+'원'
        _,carry,_,reserves,_=self.payload or ('',{},[],{}, {})
        self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
        top=ttk.Frame(self);top.grid(row=0,column=0,sticky='ew',pady=(0,10))
        cards=[('등록금회계 수입',money(carry.get('income'))),('기타이월금',money(carry.get('other'))),('누적 적립금',money(reserves.get('reserve_total'))),('검토 결과',f'충족 {passed} · 주의 {failed} · 미확인 {unknown}')]
        for col,(title,value) in enumerate(cards):
            top.columnconfigure(col,weight=1,uniform='cards')
            card=ttk.LabelFrame(top,text=title,padding=12);card.grid(row=0,column=col,sticky='nsew',padx=(0,8 if col<3 else 0))
            label=ttk.Label(card,text=value,font=NumericFont(('맑은 고딕',14,'bold')) if col<3 else ('맑은 고딕',11,'bold'));label.pack(fill='x')
            label._q.setWordWrap(True)
        palette=('#2CA66F','#F08A32','#8A9BAE')
        bottom=ttk.LabelFrame(self,text='검토 항목별 결과',padding=8);bottom.grid(row=1,column=0,sticky='ew')
        for col,weight in enumerate((1,1,2,3)):bottom.columnconfigure(col,weight=weight,uniform='results')
        for col,title in enumerate(('검토 항목','결과','주요 내용','비교 기준')):ttk.Label(bottom,text=title,style='Muted.TLabel').grid(row=0,column=col,sticky='w',padx=6,pady=3)
        for index,row in enumerate(rows,1):
            bottom.rowconfigure(index,weight=1)
            for col,text in enumerate(row):
                label=ttk.Label(bottom,text=text,anchor='w',justify='left');label.grid(row=index,column=col,sticky='nsew',padx=6,pady=3)
                if col==1:label.configure(foreground=palette[0] if text in GOOD else palette[1] if text in BAD else palette[2])
                label._q.setWordWrap(True)
