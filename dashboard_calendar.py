"""Monthly planner backed by editable schedule sheets in the existing work record book."""
import calendar
from datetime import date
from pathlib import Path
import re
import sqlite3

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from work_records import RecordBook, SECTIONS

HEADERS = (*SECTIONS['일정'], '시작', '종료', '구분')
CHECK = '체크사항'


class PlannerStore:
    def __init__(self, path):
        self.path = Path(path)

    def month(self, first):
        if not self.path.exists():
            return []
        book = RecordBook(self.path)
        with book.transaction() as db:
            tasks = [tid for tid, in db.execute('SELECT task FROM grid_cells WHERE row_num=0 AND col_num=0 AND value=?',
                                                (HEADERS[0],))]
            events = []
            for tid in tasks:
                headers = dict(db.execute('SELECT col_num,value FROM grid_cells WHERE task=? AND row_num=0',(tid,)))
                if tuple(headers.get(i) for i in range(4)) != HEADERS[:4]:
                    continue
                rows = db.execute('''SELECT c.row_num,c.col_num,c.value FROM grid_cells c JOIN grid_cells d
                    ON d.task=c.task AND d.row_num=c.row_num AND d.col_num=0
                    WHERE c.task=? AND c.row_num>0 AND c.col_num<7 AND d.value LIKE ?''',
                    (tid, first.strftime('%Y-%m')+'-%'))
                entries = {}
                for r,col,value in rows:
                    if col<4 or headers.get(col)==HEADERS[col]:
                        entries.setdefault(r, ['']*7)[col] = value
                for r, values in entries.items():
                    if values[1]:
                        events.append(((tid,r), values))
            return sorted(events,key=lambda e:(e[1][0],e[1][4],e[1][1]))

    def save(self, key, values):
        book = RecordBook(self.path)
        with book.transaction() as db:
            db.execute('BEGIN IMMEDIATE')
            if key is None:
                name = '대시보드 업무 일정'
                suffix = 1
                while True:
                    task = db.execute('SELECT id FROM tasks WHERE name=?',(name,)).fetchone()
                    if not task:
                        tid = db.execute('INSERT INTO tasks(name) VALUES(?)',(name,)).lastrowid
                        db.executemany('INSERT INTO grid_cells VALUES(?,0,?,?)',((tid,i,h) for i,h in enumerate(HEADERS)))
                        break
                    tid = task[0]
                    header = dict(db.execute('SELECT col_num,value FROM grid_cells WHERE task=? AND row_num=0',(tid,)))
                    if all(header.get(i)==h for i,h in enumerate(HEADERS)):
                        break
                    suffix += 1
                    name = f'대시보드 업무 일정 ({suffix})'
                r = db.execute('SELECT MAX(row_num)+1 FROM grid_cells WHERE task=?',(tid,)).fetchone()[0]
            else:
                tid,r = key
            for col,val in values.items():
                if col>=4:
                    head = db.execute('SELECT value FROM grid_cells WHERE task=? AND row_num=0 AND col_num=?',(tid,col)).fetchone()
                    if head and head[0]!=HEADERS[col]:
                        if val:
                            raise ValueError('업무 기록장의 사용자 열과 겹칩니다. 해당 시트에서 수정하세요.')
                        continue
                    db.execute('INSERT OR IGNORE INTO grid_cells VALUES(?,0,?,?)',(tid,col,HEADERS[col]))
                if val:
                    db.execute('INSERT INTO grid_cells VALUES(?,?,?,?) ON CONFLICT(task,row_num,col_num) DO UPDATE SET value=excluded.value',
                               (tid,r,col,val))
                else:
                    db.execute('DELETE FROM grid_cells WHERE task=? AND row_num=? AND col_num=?',(tid,r,col))


class CalendarPanel(W.QWidget):
    changed = C.Signal()

    def __init__(self, path):
        super().__init__()
        self.store = PlannerStore(path)
        self.day = date.today()
        self.events = []
        self.layout_grid = W.QGridLayout(self)
        self.layout_grid.setContentsMargins(0,0,0,0)
        left = self.left = W.QGroupBox('월간 업무 달력')
        layout = W.QVBoxLayout(left)
        bar = W.QHBoxLayout()
        layout.addLayout(bar)
        self.month_title = W.QLabel()
        for title, fn in [('‹',lambda:self.shift(-1)),('›',lambda:self.shift(1)),('오늘',lambda:self.select(date.today()))]:
            btn = W.QPushButton(title)
            btn.clicked.connect(fn)
            if title=='‹':
                btn.setAccessibleName('이전 달')
            elif title=='›':
                btn.setAccessibleName('다음 달')
            bar.addWidget(btn)
            if title=='‹':
                bar.addWidget(self.month_title)
        bar.addStretch()
        add = W.QPushButton('+ 일정 추가')
        add.clicked.connect(lambda:self.edit())
        bar.addWidget(add)
        self.grid = W.QTableWidget(0,7)
        self.grid.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.grid.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.verticalHeader().hide()
        self.grid.horizontalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch)
        self.grid.verticalHeader().setSectionResizeMode(W.QHeaderView.ResizeMode.Stretch)
        self.grid.setHorizontalHeaderLabels(list('일월화수목금토'))
        self.grid.setMinimumHeight(230)
        self.grid.currentCellChanged.connect(self.pick)
        layout.addWidget(self.grid)
        right = self.right = W.QWidget()
        side = W.QVBoxLayout(right)
        side.setContentsMargins(0,0,0,0)
        self.agenda_box = W.QGroupBox()
        schedule = W.QVBoxLayout(self.agenda_box)
        self.agenda = W.QListWidget()
        self.agenda.itemDoubleClicked.connect(lambda i:self.edit(i))
        schedule.addWidget(self.agenda)
        edit_button = W.QPushButton('선택 일정 수정')
        edit_button.clicked.connect(lambda:self.edit(self.agenda.currentItem()) if self.agenda.currentItem() else None)
        schedule.addWidget(edit_button)
        side.addWidget(self.agenda_box)
        checks = W.QGroupBox('주요 체크사항')
        ck = W.QVBoxLayout(checks)
        self.checks = W.QListWidget()
        self.checks.itemChanged.connect(self.toggle)
        self.checks.itemDoubleClicked.connect(lambda i:self.edit(i,True))
        ck.addWidget(self.checks)
        add_check = W.QPushButton('+ 체크사항 추가')
        add_check.clicked.connect(lambda:self.edit(check=True))
        ck.addWidget(add_check)
        side.addWidget(checks)
        for view in (self.agenda,self.checks):
            view.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Ignored)
            view.setMinimumHeight(48)
            view.setWordWrap(True)
        self.arrange(False)
        self.reload()

    def arrange(self,narrow):
        self.layout_grid.addWidget(self.left,0,0)
        self.layout_grid.addWidget(self.right,int(narrow),int(not narrow))
        self.layout_grid.setColumnStretch(0,3)
        self.layout_grid.setColumnStretch(1,int(not narrow))

    def shift(self,delta):
        y,m = divmod(self.day.year*12+self.day.month-1+delta,12)
        self.select(date(y,m+1,min(self.day.day,calendar.monthrange(y,m+1)[1])))

    def select(self,day):
        self.day = day
        self.reload()

    def reload(self):
        try:
            self.events = self.store.month(self.day)
        except (OSError,ValueError, sqlite3.Error) as exc:
            self.events = []
            self.agenda_box.setTitle('일정 조회 실패')
            self.agenda.clear()
            self.checks.clear()
            self.agenda.addItem(str(exc))
            return
        weeks = calendar.Calendar(6).monthdayscalendar(self.day.year,self.day.month)
        self.grid.blockSignals(True)
        self.grid.clearContents()
        self.grid.setRowCount(len(weeks))
        self.month_title.setText(f'{self.day.year}년 {self.day.month}월')
        for row,week in enumerate(weeks):
            for col,n in enumerate(week):
                if not n:
                    continue
                day = self.day.replace(day=n)
                entries = [e[1][1] for e in self.events if e[1][0]==day.isoformat()]
                item = W.QTableWidgetItem(str(n)+ ('\n'+entries[0] if entries else ''))
                item.setData(C.Qt.ItemDataRole.UserRole,n)
                item.setToolTip('\n'.join(entries))
                item.setTextAlignment(C.Qt.AlignmentFlag.AlignTop|C.Qt.AlignmentFlag.AlignLeft)
                if col in (0,6):
                    item.setForeground(G.QColor('#A43D53' if col==0 else '#475CB0'))
                self.grid.setItem(row,col,item)
                if day==self.day:
                    self.grid.setCurrentCell(row,col)
        self.grid.blockSignals(False)
        self.show_day()

    def pick(self,row,col,*_):
        item = self.grid.item(row,col)
        if item and item.data(C.Qt.ItemDataRole.UserRole):
            self.day = self.day.replace(day=item.data(C.Qt.ItemDataRole.UserRole))
            self.show_day()

    def show_day(self):
        self.agenda_box.setTitle(f'{self.day.month}월 {self.day.day}일 일정')
        self.agenda.clear()
        self.checks.blockSignals(True)
        self.checks.clear()
        for key,v in self.events:
            if v[0]!=self.day.isoformat():
                continue
            check = v[6]==CHECK
            title = ' – '.join(filter(None,v[4:6]))
            item = W.QListWidgetItem('  '.join(filter(None,(title,v[1]))))
            item.setData(C.Qt.ItemDataRole.UserRole,(key,v))
            item.setToolTip(item.text())
            (self.checks if check else self.agenda).addItem(item)
            if check:
                item.setCheckState(C.Qt.CheckState.Checked if v[3]=='완료' else C.Qt.CheckState.Unchecked)
        self.checks.blockSignals(False)
        if not self.agenda.count():
            item = W.QListWidgetItem('등록된 일정 없음')
            item.setFlags(C.Qt.ItemFlag.NoItemFlags)
            self.agenda.addItem(item)

    def persist(self,key,changes):
        try:
            self.store.save(key,changes)
            self.changed.emit()
            return True
        except (OSError,ValueError,sqlite3.Error) as exc:
            W.QMessageBox.warning(self,'일정 저장',str(exc))
            return False

    def toggle(self,item):
        data = item.data(C.Qt.ItemDataRole.UserRole)
        if data:
            self.persist(data[0],{3:'완료' if item.checkState()==C.Qt.CheckState.Checked else '진행 중'})
            self.reload()

    def edit(self,item=None,check=False):
        data = item.data(C.Qt.ItemDataRole.UserRole) if item else None
        if item and not data:
            return
        key,values = data or (None,[self.day.isoformat(),'','','','','',''])
        dialog = W.QDialog(self)
        dialog.setWindowTitle(('체크사항' if check else '일정')+(' 수정' if key else ' 추가'))
        form = W.QFormLayout(dialog)
        title = W.QLineEdit(values[1])
        day = W.QDateEdit(C.QDate.fromString(values[0],'yyyy-MM-dd'))
        day.setDisplayFormat('yyyy-MM-dd')
        day.setCalendarPopup(True)
        form.addRow('날짜',day)
        form.addRow('할 일',title)
        times = [W.QLineEdit(v) for v in values[4:6]]
        if not check:
            for label,field in zip(('시작','종료'),times):
                field.setPlaceholderText('HH:mm')
                form.addRow(label,field)
        buttons = W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Save|W.QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def submit():
            start,end = [w.text().strip() for w in times]
            if not title.text().strip() or any(v and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v) for v in (start,end)) or end and (not start or end<start):
                W.QMessageBox.warning(dialog,'입력 확인','할 일과 시간 범위를 확인하세요.')
                return
            chosen = day.date().toPython()
            if self.persist(key,{0:chosen.isoformat(),1:title.text().strip(),4:start,5:end,6:CHECK if check else '일정'}):
                self.select(chosen)
                dialog.accept()
        buttons.accepted.connect(submit)
        dialog.exec()
