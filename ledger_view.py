"""On-demand account ledger with a virtual continuous table and one total row."""
from pathlib import Path
from decimal import Decimal
import re
import qt_ui as tk
from qt_ui import ttk,filedialog,messagebox
from finance_data import LEDGER_COLUMNS,LEDGER_DISPLAY_COLUMNS,BUSINESS_COLUMNS,filter_ledger,ledger_totals,export_ledger
from ledger_layout import COMPACT_COLUMNS,fit_ledger_columns
from statement_catalog import amount_text


class LedgerModel(tk.C.QAbstractTableModel):
    def __init__(self,view,window):
        super().__init__(view);self.view=view;self.window=window;self.records=[];self.columns=COMPACT_COLUMNS;self.totals={};self.ready=False
    def replace(self,records,totals,columns,ready=True):
        self.beginResetModel();self.records=records;self.totals=totals;self.columns=list(columns);self.ready=ready;self.endResetModel()
    def rowCount(self,parent=tk.C.QModelIndex()):return 0 if parent.isValid() else len(self.records)+int(self.ready)
    def columnCount(self,parent=tk.C.QModelIndex()):return 0 if parent.isValid() else len(self.columns)
    def headerData(self,section,orientation,role=tk.C.Qt.ItemDataRole.DisplayRole):
        if role!=tk.C.Qt.ItemDataRole.DisplayRole:return None
        return self.columns[section] if orientation==tk.C.Qt.Orientation.Horizontal else ('합계' if section==len(self.records) else str(section+1))
    def data(self,index,role=tk.C.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        column=self.columns[index.column()];total=index.row()==len(self.records)
        value=(self.totals.get(column,'전체 합계' if index.column()==0 else '') if total else self.records[index.row()].get(column,''))
        numeric=column in ('차변','대변')
        if role in (tk.C.Qt.ItemDataRole.DisplayRole,tk.C.Qt.ItemDataRole.ToolTipRole):return amount_text(value) if isinstance(value,Decimal) else str(value)
        if role==tk.C.Qt.ItemDataRole.UserRole:return value
        if role==tk.C.Qt.ItemDataRole.TextAlignmentRole:return int(tk.C.Qt.AlignmentFlag.AlignVCenter|(tk.C.Qt.AlignmentFlag.AlignRight if numeric else tk.C.Qt.AlignmentFlag.AlignLeft))
        if role==tk.C.Qt.ItemDataRole.BackgroundRole and total:return tk.G.QColor('#38566B')
        if role==tk.C.Qt.ItemDataRole.ForegroundRole and total:return tk.G.QColor('#FFFFFF')
        if role==tk.C.Qt.ItemDataRole.FontRole:
            from appearance import controller
            appearance=controller(self.window);font=tk.G.QFont(self.view.font())
            if appearance:font.setFamily((appearance.numeric_family or appearance.family) if numeric else appearance.family)
            font.setBold(total)
            if appearance and getattr(appearance,'text_sizes',None):font.setPointSizeF(appearance.text_sizes['data'])
            return tk.readable_font(font)


class PeriodDate(tk.W.QWidget):
    def __init__(self,name):
        super().__init__();self.setAccessibleName(name)
        layout=tk.W.QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        self.entry=tk.W.QLineEdit();self.entry.setAccessibleName(name);self.entry.setPlaceholderText('YYYY-MM-DD');self.entry.setMinimumWidth(120)
        self.entry.editingFinished.connect(self.interpretText);layout.addWidget(self.entry)
        button=tk.W.QToolButton();button.setAccessibleName(name+' 달력');button.setToolTip('달력에서 날짜 선택')
        button.setIcon(tk.G.QIcon(str(Path(__file__).resolve().parent/'assets'/'calendar.svg')));button.setIconSize(tk.C.QSize(20,20));layout.addWidget(button)
        self.popup=tk.W.QFrame(self,tk.C.Qt.WindowType.Popup)
        popup_layout=tk.W.QVBoxLayout(self.popup);self.calendar=tk.W.QCalendarWidget();popup_layout.addWidget(self.calendar)
        def picked(date):self.setDate(date);self.popup.hide()
        self.calendar.clicked.connect(picked)
        def show():
            try:date=self.parsed()
            except ValueError:date=tk.C.QDate.currentDate()
            self.calendar.setSelectedDate(date if date.isValid() else tk.C.QDate.currentDate())
            self.popup.adjustSize();point=self.mapToGlobal(tk.C.QPoint(0,self.height()))
            screen=self.screen().availableGeometry()
            point.setX(max(screen.left(),min(point.x(),screen.right()-self.popup.width()+1)))
            if point.y()+self.popup.height()>screen.bottom():point.setY(self.mapToGlobal(tk.C.QPoint()).y()-self.popup.height())
            self.popup.move(point);self.popup.show()
        button.clicked.connect(show)
    def lineEdit(self):return self.entry
    def calendarPopup(self):return True
    def calendarWidget(self):return self.calendar
    def parsed(self):
        text=self.entry.text().strip()
        if not text:return tk.C.QDate()
        digits=re.sub(r'[-./]','',text)
        date=tk.C.QDate.fromString(digits,'yyyyMMdd') if re.fullmatch(r'\d{8}',digits) else tk.C.QDate()
        if not date.isValid():raise ValueError('기간은 YYYY-MM-DD 또는 YYYYMMDD 형식으로 입력하세요.')
        return date
    def value(self):
        date=self.parsed();return date.toString('yyyy-MM-dd') if date.isValid() else ''
    def setDate(self,date):self.entry.setText(date.toString('yyyy-MM-dd'))
    def clear_period(self):self.entry.clear()
    def interpretText(self):
        try:
            date=self.parsed()
            if date.isValid():self.setDate(date)
        except ValueError:pass


def open_ledger(parent,desktop,center,open_file):
    from finance_ui import shell,target_file,saved
    from audit_review import AccountOrder,matches
    from analysis_runtime import load_program_ledger,program_statement_paths
    from audit_review import load_statement_history
    window,body,status,jobs=shell(parent,'계정별원장 조회',center)
    records=[];paths={};order=AccountOrder();source=None;notes=[]
    top=ttk.Frame(body);top.pack(fill='x',pady=(0,8))
    ttk.Label(top,text='원장 연도').pack(side='left',padx=(0,6))
    year=tk.StringVar();year_box=ttk.Combobox(top,textvariable=year,state='readonly',width=8);year_box.pack(side='left',padx=(0,10));jobs.controls.append(year_box)
    label=tk.StringVar(value='원장 자료 확인 중');ttk.Label(top,textvariable=label,style='Muted.TLabel').pack(side='left')
    from responsive_ui import wrapping_row
    filters={};boxes={};filterbar=wrapping_row(body);filterbar.pack(fill='x')
    fields=['회계단위','관','항','목',*BUSINESS_COLUMNS]
    for name in fields:
        cell=ttk.Frame(filterbar);cell.pack(side='left')
        ttk.Label(cell,text=name).pack(anchor='w',pady=(0,4))
        variable=tk.StringVar(value='전체');filters[name]=variable
        box=ttk.Combobox(cell,textvariable=variable,state='readonly',values=['전체'],width=6);box.pack(fill='x')
        box._q.setAccessibleName(name);boxes[name]=box;jobs.controls.append(box)
    bar=ttk.Frame(body);bar.pack(fill='x',pady=10)
    layout=tk.W.QHBoxLayout(bar._q);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
    layout.addWidget(tk.W.QLabel('기간 :'))
    start=PeriodDate('기간 시작일');end=PeriodDate('기간 종료일')
    layout.addWidget(start);layout.addWidget(tk.W.QLabel('–'));layout.addWidget(end);layout.addSpacing(8)
    layout.addWidget(tk.W.QLabel('거래선·적요 등'))
    search=tk.W.QLineEdit();search.setAccessibleName('거래선·적요 등');search.setMaximumWidth(320);layout.addWidget(search,1)
    all_columns=tk.W.QCheckBox('전체 열 표시');layout.addWidget(all_columns);layout.addStretch()
    totals=tk.StringVar();ttk.Label(body,textvariable=totals,style='Accent.TLabel').pack(fill='x',pady=(0,6))
    host=ttk.Frame(body);host.pack(fill='both',expand=True);table_layout=tk.W.QVBoxLayout(host._q);table_layout.setContentsMargins(0,0,0,0)
    view=tk.W.QTableView();table_layout.addWidget(view);model=LedgerModel(view,window);view.setModel(model)
    view.setSortingEnabled(False);view.setWordWrap(False);view.setAlternatingRowColors(True)
    view.setEditTriggers(tk.W.QAbstractItemView.EditTrigger.NoEditTriggers);view.setSelectionBehavior(tk.W.QAbstractItemView.SelectionBehavior.SelectRows)
    view.setVerticalScrollMode(tk.W.QAbstractItemView.ScrollMode.ScrollPerPixel);view.horizontalHeader().setStretchLastSection(False)
    window._ledger_table=view;window._ledger_model=model;window._ledger_dates=(start,end)
    def fit(event=None):
        metrics=tk.G.QFontMetrics(view.font());names=model.columns
        widths=[]
        for column,name in enumerate(names):
            widths.append(max([metrics.horizontalAdvance(name)+28]+[metrics.horizontalAdvance(str(model.index(row,column).data() or ''))+24 for row in range(min(500,model.rowCount()))]+[metrics.horizontalAdvance(amount_text(model.totals.get(name,0)))+28 if name in ('차변','대변') else 0]))
        for column,width in enumerate(fit_ledger_columns(names,widths,view.viewport().width())):view.setColumnWidth(column,width)
        view.verticalHeader().setDefaultSectionSize(max(28,metrics.height()+8))
    window.bind('<<ThemeChanged>>',fit,add='+');host.bind('<Configure>',fit,add='+')
    def columns_changed():model.replace(model.records,model.totals,LEDGER_DISPLAY_COLUMNS if all_columns.isChecked() else COMPACT_COLUMNS,model.ready);fit()
    all_columns.toggled.connect(columns_changed)
    def empty():
        model.replace([],{},model.columns,False);totals.set('');status.set('조건을 선택하거나 조회를 눌러 내역을 불러오세요.')
    def choices(data,order,values):
        result={}
        for i,name in enumerate(fields):
            subset=[row for row in data if matches(row,{key:values[key] for key in fields[:i]})]
            result[name]=['전체']+(order.choices(subset,name) if name in ('관','항','목') else list(dict.fromkeys(row[name] for row in subset if row.get(name) and row[name]!='전체')))
        return result
    def show_choices(options):
        for name,values in options.items():
            boxes[name].configure(values=values)
            metrics=tk.G.QFontMetrics(boxes[name]._q.font());width=max(metrics.horizontalAdvance(str(v)) for v in values)+46
            boxes[name]._q.setMinimumWidth(0);boxes[name]._q.setFixedWidth(max(88,width))
    def apply(changed=None):
        if jobs.busy or source is None:return
        if changed:
            for name in fields[fields.index(changed)+1:]:filters[name].set('전체')
        values={name:var.get() for name,var in filters.items()};query=search.text()
        try:dates=(start.value(),end.value())
        except ValueError as error:messagebox.showerror('조회 조건',str(error),parent=window);return
        def work():
            found=filter_ledger([row for row in records if matches(row,values)],{},*dates,query)
            return found,ledger_totals(found),choices(records,order,values)
        def done(payload):
            found,amount,options=payload;show_choices(options)
            model.replace(found,amount,model.columns);fit();view.scrollToTop()
            totals.set(f'{len(found):,}건 · 차변 {amount_text(amount["차변"])}원 · 대변 {amount_text(amount["대변"])}원')
            status.set('조회 완료 · 아래로 스크롤하면 내역 전체와 마지막 합계 행을 볼 수 있습니다.'+(' / '+' / '.join(notes) if notes else ''))
        jobs.run(work,done)
    for name,box in boxes.items():box.bind('<<ComboboxSelected>>',lambda e,k=name:apply(k))
    search.returnPressed.connect(apply)
    start.lineEdit().returnPressed.connect(apply);end.lineEdit().returnPressed.connect(apply)
    def load_year(event=None):
        nonlocal records,source
        if jobs.busy:return
        source=None;records=[];empty()
        for var in filters.values():var.set('전체')
        start.clear_period();end.clear_period();search.clear()
        path=paths.get(year.get())
        if path is None:return
        requested=year.get();label.set(f'{requested}회계연도 계정별원장')
        def work():
            rows=load_program_ledger(path,requested)
            folder=next(iter(program_statement_paths().values())).parent
            history,errors,_=load_statement_history(folder.parent)
            ordering=AccountOrder(history,rows);rows.sort(key=ordering.key)
            return rows,ordering,errors,choices(rows,ordering,{name:'전체' for name in fields})
        def done(payload):
            nonlocal records,order,notes,source
            records,order,notes,options=payload;source=path;show_choices(options);empty()
            status.set('원장 준비 완료 · 조건을 선택하거나 조회를 누르세요.')
        jobs.run(work,done)
    year_box.bind('<<ComboboxSelected>>',load_year)
    def refresh():
        nonlocal paths
        if jobs.busy:return
        from ledger_database import discover_years
        paths=discover_years();year_box.configure(values=list(paths))
        if not paths:empty();label.set('저장된 원장 없음');return
        if year.get() not in paths:year.set(next(iter(paths)))
        load_year()
    def choose():
        if jobs.busy:return
        filename=filedialog.askopenfilename(parent=window,filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
        if not filename:return
        path=Path(filename);match=re.search(r'20\d{2}',path.stem);key=match.group() if match else path.stem
        paths[key]=path;year_box.configure(values=list(paths));year.set(key);load_year()
    def reset():
        if jobs.busy:return
        for var in filters.values():var.set('전체')
        start.clear_period();end.clear_period();search.clear();empty()
        def done(options):show_choices(options);status.set('조건을 선택하거나 조회를 눌러 내역을 불러오세요.')
        jobs.run(lambda:choices(records,order,{name:'전체' for name in fields}),done)
    def export():
        if jobs.busy or not model.ready:return
        target=target_file(window,None,'계정별원장 조회');snapshot=list(model.records)
        if Path(target).resolve() in {p.resolve() for p in paths.values()}:return
        jobs.run(lambda:export_ledger(snapshot,target,include_summary=False),lambda path:saved(window,status,open_file,path))
    def detail(index):
        if not index.isValid() or index.row()>=len(model.records):return
        row=model.records[index.row()];dialog=tk.Toplevel(window);dialog.title('계정별원장 · 거래 상세');center(dialog,820,620)
        text=tk.Text(dialog,wrap='word');text.pack(fill='both',expand=True)
        text.insert('1.0','\n\n'.join(f'{key}: {amount_text(value) if isinstance(value,Decimal) else value}' for key,value in row.items()));text.configure(state='disabled')
    view.doubleClicked.connect(detail)
    for title,callback in [('Excel 저장',export),('조건 초기화',reset),('조회',apply),('원장 파일 선택',choose),('연도 새로고침',refresh)]:
        button=ttk.Button(top,text=title,command=callback);button.pack(side='right',padx=4);jobs.controls.append(button)
    window.after(100,refresh)
    return window
