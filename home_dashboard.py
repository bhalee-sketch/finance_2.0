"""Home workspace: independently selectable financial scope and work calendar."""
from itertools import zip_longest

from PySide6 import QtGui as G, QtWidgets as W

from dashboard_calendar import CalendarPanel
from dashboard_finance import (Period, SCOPE_NAMES, complete_sum, difference, load_dashboard,
                               millions, won, year_end)
from dashboard_widgets import BalanceTable, DataTable, Trend, background


class Card(W.QGroupBox):
    def __init__(self,title,detail=None):
        super().__init__(title)
        self.setObjectName("DashboardCard")
        self.setMinimumWidth(0)
        self.body = W.QVBoxLayout(self)
        line = W.QHBoxLayout()
        self.body.addLayout(line)
        self.basis = W.QLabel()
        self.basis.setWordWrap(True)
        line.addWidget(self.basis,1)
        if detail:
            self.more = W.QPushButton('상세')
            self.more.setAccessibleName(title+' 상세보기')
            self.more.clicked.connect(detail)
            line.addWidget(self.more)
        self.note = W.QLabel()
        self.note.setWordWrap(True)
        self.body.addWidget(self.note)

    def content(self,widget):
        self.body.insertWidget(1,widget,1)


class Dashboard(W.QScrollArea):
    def __init__(self,settings,open_loans):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(W.QFrame.Shape.NoFrame)
        self.data = None
        self.scope = '전체'
        self.open_loans = open_loans
        self.mode = None
        panel = W.QWidget()
        self.setWidget(panel)
        layout = W.QVBoxLayout(panel)
        head = W.QHBoxLayout()
        title = W.QLabel('재무회계 대시보드')
        title.setObjectName('DashboardTitle')
        title.setStyleSheet('font-weight:700; font-size:16pt;')
        head.addWidget(title)
        head.addStretch()
        head.addWidget(W.QLabel('회계 구분'))
        self.selector = W.QComboBox()
        for key,name in SCOPE_NAMES.items():
            self.selector.addItem(name,key)
        head.addWidget(self.selector)
        layout.addLayout(head)
        self.status = W.QLabel('재무제표 조회 중…')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.cards = W.QGridLayout()
        layout.addLayout(self.cards)
        self.cash = Card('자금계산서 총액',lambda:self.detail('자금계산서'))
        self.balance = Card('재무상태표',lambda:self.detail('재무상태표'))
        self.operation = Card('운영계산서',lambda:self.detail('운영계산서'))
        self.fund = Card('임의기금',lambda:self.detail('임의기금'))
        self.trends = {}
        for key,card,labels,line in [('cash',self.cash,['총액'],False),('operation',self.operation,['운영수익','운영비용'],True),
                                     ('fund',self.fund,['임의기금 잔액'],False)]:
            chart = Trend(labels,line)
            card.content(chart)
            self.trends[key] = chart
        self.t_table = BalanceTable()
        self.balance.content(self.t_table)
        self.loan = Card('차입금 잔액')
        self.loan_amount = W.QPushButton('조회 중…')
        self.loan_amount.setStyleSheet('font-weight:700; font-size:13pt;')
        self.loan_amount.clicked.connect(self.show_loans)
        self.loan.body.insertWidget(0,self.loan_amount)
        self.loan_amount.setObjectName("DashboardLoanAmount")
        self.right = W.QWidget()
        stack = W.QVBoxLayout(self.right)
        stack.setContentsMargins(0,0,0,0)
        stack.addWidget(self.fund,1)
        stack.addWidget(self.loan)
        self.planner = CalendarPanel(settings/'업무 기록.sqlite3')
        layout.addWidget(self.planner,1)
        self.selector.currentIndexChanged.connect(self.filter_changed)
        self.arrange()
        self.set_finance_enabled(False)
        background(self,load_dashboard,self.loaded,self.failed)

    def set_finance_enabled(self,enabled):
        for card in (self.cash,self.balance,self.operation,self.fund):
            card.more.setEnabled(enabled)
        self.loan_amount.setEnabled(enabled)

    def failed(self,error):
        self.set_finance_enabled(False)
        self.status.setText(f'재무제표 조회 실패 · {error}')
        self.loan_amount.setText('조회 실패')
        for chart in self.trends.values():
            chart.set_rows([], '조회 실패')

    def loaded(self,data):
        self.data = data
        self.render()

    def filter_changed(self):
        self.scope = self.selector.currentData()
        if self.data is not None:
            self.render()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'planner'):
            self.arrange()

    def arrange(self):
        width = self.viewport().width()
        mode = 4 if width>=1310 else 2 if width>=945 else 1
        if mode==self.mode:
            return
        self.mode = mode
        for i,card in enumerate((self.cash,self.balance,self.operation,self.right)):
            self.cards.addWidget(card,i//mode,i%mode)
        for i in range(4):
            self.cards.setColumnStretch(i,(2 if i==1 and mode==4 else 1) if i<mode else 0)
        self.planner.arrange(width<770)

    def render(self):
        years = self.data.years
        self.set_finance_enabled(bool(years))
        if not years:
            self.status.setText('재무제표 자료 없음')
            for chart in self.trends.values():
                chart.set_rows([])
            self.loan_amount.setText('자료 없음')
            return
        scope = SCOPE_NAMES[self.scope]
        latest = self.data.periods.get((years[-1], self.scope), Period())
        status = '최근 연도 미확정' if any('미확정' in issue for issue in latest.errors.values()) else '확정결산'
        self.status.setText(f'{years[0]}–{years[-1]}회계연도 · {status} · {scope}')
        series = {k:[] for k in self.trends}
        notes = {k:[] for k in self.trends}
        for year in years:
            p = self.data.periods.get((year,self.scope),Period())
            delta = difference(*p.cash)
            values = {'cash':(p.cash[0] if delta==0 else None,), 'operation':p.operation,
                      'fund':(p.balance.fund if p.balance else None,)}
            for key,kind in [('cash','자금계산서'),('operation','운영계산서'),('fund','재무상태표')]:
                series[key].append((year,values[key]))
                if kind in p.errors:
                    notes[key].append(f'{year} 확인 필요 · {p.errors[kind]}')
                elif key=='cash' and delta not in (None,0):
                    notes[key].append(f'{year} 확인 필요 · 차이 {won(delta)}')
                elif None in values[key]:
                    notes[key].append(f'{year} 자료 없음')
        for key,card in [('cash',self.cash),('operation',self.operation),('fund',self.fund)]:
            self.trends[key].set_rows(series[key])
            card.basis.setText(f'{years[0]}–{years[-1]} · {scope} · 억 원')
            card.note.setText('\n'.join(notes[key]))
            card.note.setVisible(bool(notes[key]))
        year,b = self.data.latest_balance(self.scope)
        self.balance.more.setEnabled(b is not None)
        self.loan_amount.setEnabled(b is not None)
        if b is None:
            self.balance.basis.setText('자료 없음')
            self.t_table.setRowCount(0)
            self.balance.note.clear()
            self.loan_amount.setText('자료 없음')
            self.loan.basis.clear()
            return
        self.balance.basis.setText(f'{year_end(year)} · {scope}\n단위: 백만원')
        capital = b.capital_items
        right = [*b.liabilities,('부채 소계',b.debt),*capital,('기본금 소계',b.equity)]
        paired = list(zip_longest(b.assets,right,fillvalue=None))
        paired.append((('자산총계',b.left_total),('부채 및 기본금 총계',b.right_total)))
        values = []
        for pair in paired:
            row = []
            for part in pair:
                if part is None:
                    row.extend(['',''])
                else:
                    name,val = part
                    row.extend([name, '자료 없음' if val is None else f'{millions(val):,}'])
            values.append(row)
        self.t_table.populate(['자산','금액','부채 및 기본금','금액'],values)
        for i,pair in enumerate(paired):
            for j,part in enumerate(pair):
                if part is None:
                    continue
                label,val = part
                for col in (2*j,2*j+1):
                    cell = self.t_table.item(i,col)
                    cell.setToolTip(f'{label}  {won(val)}')
                    if i==len(paired)-1 or label.endswith('소계'):
                        font=cell.font()
                        font.setBold(True)
                        cell.setFont(font)
                        palette = self.palette()
                        cell.setBackground(palette.color(G.QPalette.ColorRole.AlternateBase))
        self.t_table.fit()
        self.t_table.resizeRowsToContents()
        self.t_table.setMinimumHeight(self.t_table.verticalHeader().length()+self.t_table.horizontalHeader().height()+
                                      self.t_table.horizontalScrollBar().sizeHint().height()+4)
        notes = [f'{label} {won(diff)}' for label,diff in b.checks.items() if diff!=0]
        text = '확인 필요 · '+' / '.join(notes) if notes else '원 단위 합계 일치'
        if b.rounding_note:
            text += '\n백만원 반올림으로 항목 합과 표시 총계에 차이가 있습니다.'
        self.balance.note.setText(text)
        self.loan_amount.setText(won(complete_sum(b.loan_parts)))
        self.loan.basis.setText(f'{year_end(year)} 기준 · {scope}')
        self.loan.note.hide()

    def show_loans(self):
        if self.data:
            year,b = self.data.latest_balance(self.scope)
            if b:
                self.open_loans(self.data,year,self.scope)

    def detail(self,kind):
        dlg = W.QDialog(self)
        dlg.setWindowTitle(f'{kind} 상세 · {SCOPE_NAMES[self.scope]}')
        layout = W.QVBoxLayout(dlg)
        grid = DataTable()
        years = self.data.years
        if kind=='재무상태표':
            year,b = self.data.latest_balance(self.scope)
            if not b:
                return
            basis = f'{year_end(year)} 기준 · 재무상태표({self.scope}) 당기'
            rows = [(section,' / '.join(path),won(v)) for section,path,v in b.accounts]
            rows.extend([('자산','자산총계',won(b.left_total)),('부채와기본금','부채 및 기본금 총계',won(b.right_total))])
            grid.populate(['구분','계정과목','금액'],rows)
        else:
            basis = f'{years[0]}–{years[-1]}회계연도 · {SCOPE_NAMES[self.scope]}'
            rows = []
            for y in years:
                p = self.data.periods.get((y,self.scope),Period())
                if kind=='자금계산서':
                    diff = difference(*p.cash)
                    rows.append((y,won(p.cash[0]),won(p.cash[1]),won(diff),'자료 없음' if diff is None else '일치' if diff==0 else '확인 필요'))
                elif kind=='운영계산서':
                    rows.append((y,*(won(v) for v in p.operation)))
                else:
                    rows.append((y,won(p.balance.fund if p.balance else None)))
            headers = {'자금계산서':['연도','자금수입총계','자금지출총계','차이','검증'],
                       '운영계산서':['연도','운영수익 총계','운영비용 총계'],'임의기금':['연도','임의기금 잔액']}
            grid.populate(headers[kind], rows)
        layout.addWidget(W.QLabel(basis+' · 단위: 원'))
        layout.addWidget(grid)
        dlg.resize(min(self.window().width(),850),min(self.window().height(),540))
        dlg.exec()
