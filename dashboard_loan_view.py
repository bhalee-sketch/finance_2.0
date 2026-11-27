from PySide6 import QtCore as C, QtWidgets as W

from dashboard_finance import SCOPE_NAMES, complete_sum, difference, won, year_end
from dashboard_loans import detail_for
from dashboard_widgets import DataTable, background


class ClosingLoanView(W.QWidget):
    def __init__(self, storage):
        super().__init__()
        self.storage = storage
        self.context = None
        self.request = 0
        self.result = None
        layout = W.QVBoxLayout(self)
        self.caption = W.QLabel()
        self.status = W.QLabel()
        for label in (self.caption, self.status):
            label.setWordWrap(True)
            layout.addWidget(label)
        basis = W.QLabel('잔액은 결산 명세서 기준입니다. 상환일정은 현재 등록된 원자료에서 결산 기준일 이후의 예정 내역을 표시합니다.')
        basis.setWordWrap(True)
        layout.addWidget(basis)
        controls = W.QHBoxLayout()
        controls.addWidget(W.QLabel('차입처'))
        self.lenders = W.QComboBox()
        self.lenders.setAccessibleName('차입처')
        self.lenders.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.lenders.currentIndexChanged.connect(self.filter_details)
        controls.addWidget(self.lenders)
        controls.addStretch()
        layout.addLayout(controls)
        tabs = W.QTabWidget()
        layout.addWidget(tabs)
        self.groups, self.contracts, self.schedule = (DataTable() for _ in range(3))
        for title, view in [('차입처별 잔액', self.groups), ('차입 건별 명세', self.contracts),
                            ('기준일 이후 상환일정', self.schedule)]:
            tabs.addTab(view, title)

    def filter_details(self):
        if self.result is None:
            return
        contracts, rows, lenders, total, _ = self.result
        lender = self.lenders.currentData()
        balances = [(name, won(value)) for name, value in lenders.items() if not lender or name == lender]
        balances.append(('합계', won(lenders[lender] if lender else total)))
        self.groups.populate(['차입처', '기말 잔액'], balances)
        self.contracts.populate(['차입처', '차입 건명', '기말 잔액', '금리', '명세서 만기일', '명세서 상환기한', '차입일', '명세서 항목'], [
            (c['lender'] or '미등록', c['name'], won(c['balance']), c['rate'], c['maturity'], c['term'], c['issued'], c['note_name'])
            for c in contracts if not lender or (c['lender'] or '미등록') == lender
        ])
        self.schedule.populate(['상환예정일', '차입처', '차입 건명', '원금', '이자', '합계'], [
            (due, name, project, *(won(v) if v is not None else '미등록' for v in (principal, interest, amount)))
            for due, name, project, principal, interest, amount in rows if not lender or name == lender
        ])

    def display(self, data, year, scope):
        self.context = data, year, scope
        self.request += 1
        request = self.request
        home = complete_sum(data.periods[year, scope].balance.loan_parts)
        self.caption.setText(f'{SCOPE_NAMES[scope]}  ·  {year_end(year)} 기준  ·  차입금 잔액 {won(home)}')
        self.status.setText('차입금 명세와 상환일정을 조회하고 있습니다…')
        self.result = None
        self.lenders.clear()
        self.lenders.setEnabled(False)
        for table in (self.groups, self.contracts, self.schedule):
            table.setRowCount(0)

        def done(result):
            if request != self.request:
                return
            self.result = result
            _, rows, lenders, total, alerts = result
            diff = difference(home, total)
            status = '대사 자료 없음' if diff is None else '차입처별 합계 일치' if diff == 0 else '확인 필요 · 차이 ' + won(diff)
            notices = [status, *alerts]
            if not rows:
                notices.append('상환 대상 없음' if home == total == 0 else '상환일정 미등록')
            self.status.setText('  ·  '.join(notices))
            with C.QSignalBlocker(self.lenders):
                self.lenders.addItem('전체 차입처', None)
                for name in sorted(lenders):
                    self.lenders.addItem(name, name)
            labels = [self.lenders.itemText(i) for i in range(self.lenders.count())]
            self.lenders.setMinimumWidth(max(self.lenders.fontMetrics().horizontalAdvance(label) for label in labels) + 52)
            self.lenders.setEnabled(bool(lenders))
            self.filter_details()

        def failed(exc):
            if request == self.request:
                self.status.setText('차입금 상세 조회 실패 · ' + str(exc))

        storage = self.storage
        background(self, lambda: detail_for(data, year, scope, storage), done, failed)

    def refresh(self):
        if self.context:
            self.display(*self.context)
