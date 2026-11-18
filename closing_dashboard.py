"""One-screen closing dashboard using existing review calculations only."""
import math
import qt_ui as tk
from qt_ui import ttk
from statement_catalog import amount_text
from chart_rendering import polished_chart
from appearance import NumericFont

GOOD=('일치','1.0% 이내','한도 이내')
BAD=('불일치','1.0% 초과','한도 초과')


def dashboard_rows(payload):
    if not payload:return [(name,'자료 확인 필요','—','—') for name in ('등록금 이월','기금 수입 대체','기금 지출 대체','감가상각비 내 전출','증권투자 한도')]
    year,carry,comparisons,reserves,result=payload
    money=lambda v:'—' if v is None else amount_text(v)+'원'
    ratio=carry.get('ratio')
    rows=[('등록금 이월',carry['state'],'비율 '+('—' if ratio is None else f'{ratio:.4f}%')+' / 기준 1% 이하','기타이월금 '+money(carry.get('other'))+' / 등록금 수입 '+money(carry.get('income')))]
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
        year,carry,comparisons,reserves,result=self.payload or ('',{},[],{}, {})
        self.columnconfigure(0,weight=1);self.rowconfigure(1,weight=3);self.rowconfigure(2,weight=2)
        top=ttk.Frame(self);top.grid(row=0,column=0,sticky='ew',pady=(0,10))
        cards=[('등록금회계 수입',money(carry.get('income'))),('기타이월금',money(carry.get('other'))),('누적 적립금',money(reserves.get('reserve_total'))),('검토 결과',f'충족 {passed} · 주의 {failed} · 미확인 {unknown}')]
        for col,(title,value) in enumerate(cards):
            top.columnconfigure(col,weight=1,uniform='cards')
            card=ttk.LabelFrame(top,text=title,padding=12);card.grid(row=0,column=col,sticky='nsew',padx=(0,8 if col<3 else 0))
            label=ttk.Label(card,text=value,font=NumericFont(('맑은 고딕',14,'bold')) if col<3 else ('맑은 고딕',11,'bold'));label.pack(fill='x')
            label._q.setWordWrap(True)
        middle=ttk.Frame(self);middle.grid(row=1,column=0,sticky='nsew',pady=(0,10));middle.rowconfigure(0,weight=1)
        for col in range(3):middle.columnconfigure(col,weight=1,uniform='panels')
        chart1=ttk.LabelFrame(middle,text='검토 결과 비율',padding=10);chart1.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        chart2=ttk.LabelFrame(middle,text='임의기금 대체 대사 · 백만원',padding=10);chart2.grid(row=0,column=1,sticky='nsew',padx=(0,8))
        metrics=ttk.LabelFrame(middle,text='주요 지표 · 원',padding=10);metrics.grid(row=0,column=2,sticky='nsew')
        palette=('#2CA66F','#F08A32','#8A9BAE')
        canvas=tk.Canvas(chart1,height=200,highlightthickness=0);canvas.pack(fill='both',expand=True)
        canvas._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Ignored)
        canvas._q.setMinimumSize(180,150)
        @polished_chart
        def donut(c):
            c.delete('all');w=max(180,c.winfo_width());h=max(150,c.winfo_height());r=min(w*.24,h*.30);cx=w/2;cy=h*.38;start=-90
            for count,color in zip((passed,failed,unknown),palette):
                if not count:continue
                extent=360*count/max(1,len(rows));steps=max(2,int(extent/3))
                angles=[math.radians(start+extent*i/steps) for i in range(steps+1)]
                points=[(cx+r*math.cos(a),cy+r*math.sin(a)) for a in angles]+[(cx+r*.63*math.cos(a),cy+r*.63*math.sin(a)) for a in reversed(angles)]
                c.create_polygon(*[v for point in points for v in point],fill=color,outline='');start+=extent
            c.create_text(cx,cy,text=f'총 {len(rows)}건',fill='#E2E8F0',font=('맑은 고딕',13,'bold'))
            c.create_text(w/2,h-45,text=f'충족 {passed}건   주의 {failed}건',fill='#E2E8F0')
            c.create_text(w/2,h-23,text=f'자료 확인 {unknown}건',fill='#94A3B8')
        canvas.bind('<Configure>',lambda event:donut(canvas))
        bars=tk.Canvas(chart2,height=200,highlightthickness=0);bars.pack(fill='both',expand=True)
        bars._q.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Ignored)
        bars._q.setMinimumSize(180,150)
        @polished_chart
        def draw_bars(c):
            c.delete('all');w=max(180,c.winfo_width());h=max(150,c.winfo_height())
            values=[float(item[key]) for item in comparisons for key in ('source','amount') if item.get(key) is not None]
            maximum=max([abs(v) for v in values]+[1]);baseline=h-40;room=max(40,h-100)
            c.create_text(w/2,12,text='자금계산서 / 운영계산서',fill='#94A3B8')
            for i,item in enumerate(comparisons[:2]):
                center=w*(.28+.44*i)
                for offset,key,color in [(-.10,'source','#62A8FF'),(.02,'amount','#355BA4')]:
                    x=center+w*offset;value=item.get(key)
                    if value is None:
                        c.create_text(x+w*.04,baseline-10,text='—',fill='#94A3B8');continue
                    value=float(value);height=abs(value)/maximum*room
                    c.create_polygon(x,baseline,x+w*.08,baseline,x+w*.08,baseline-height,x,baseline-height,fill=color,outline='')
                    c.create_text(x+w*.04,baseline-height-(12 if key=='source' else 28),text=f'{value/1000000:,.1f}',fill='#E2E8F0',font=('맑은 고딕',9))
                c.create_text(center,baseline+20,text=item['section']+' 대체',fill='#E2E8F0')
            if not comparisons:c.create_text(w/2,h/2,text='자료 확인 필요',fill='#94A3B8')
        bars.bind('<Configure>',lambda event:draw_bars(bars))
        details=[('미사용 차기이월자금',carry.get('carryover')),('선급금 (사고이월 가정)',carry.get('advance')),('건물감가상각비',reserves.get('depreciation')),('등록금 재원 전출',reserves.get('transfer')),('증권 투자원금',reserves.get('securities'))]
        for i,(label,value) in enumerate(details):
            metrics.rowconfigure(i,weight=1);metrics.columnconfigure(1,weight=1)
            ttk.Label(metrics,text=label).grid(row=i,column=0,sticky='w',padx=(0,8),pady=4)
            ttk.Label(metrics,text=money(value)).grid(row=i,column=1,sticky='e',pady=4)
        bottom=ttk.LabelFrame(self,text='검토 항목별 결과',padding=8);bottom.grid(row=2,column=0,sticky='nsew')
        for col,weight in enumerate((1,1,2,3)):bottom.columnconfigure(col,weight=weight,uniform='results')
        for col,title in enumerate(('검토 항목','결과','주요 내용','비교 기준')):ttk.Label(bottom,text=title,style='Muted.TLabel').grid(row=0,column=col,sticky='w',padx=6,pady=3)
        for index,row in enumerate(rows,1):
            bottom.rowconfigure(index,weight=1)
            for col,text in enumerate(row):
                label=ttk.Label(bottom,text=text,anchor='w',justify='left');label.grid(row=index,column=col,sticky='nsew',padx=6,pady=3)
                if col==1:label.configure(foreground=palette[0] if text in GOOD else palette[1] if text in BAD else palette[2])
                label._q.setWordWrap(True)
