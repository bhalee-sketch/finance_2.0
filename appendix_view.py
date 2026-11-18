"""Appendix record tables read directly from the bundled databases."""
from pathlib import Path
import qt_ui as tk
from qt_ui import ttk
from statement_database import connect
from statement_ui import Jobs
from appendix_data import load_sheet
from appendix_model import AppendixModel,display_value

DATA=Path(__file__).resolve().parent/'data'/'appendices'
SOURCES={'재무상태표':DATA/'balance.sqlite3','운영계산서':DATA/'operation.sqlite3'}


def list_sheets(kind,year='2025'):
    with connect(SOURCES[kind]) as connection:
        return [name for name, in connection.execute('SELECT s.name FROM sheets s JOIN workbooks w ON w.id=s.workbook_id WHERE w.fiscal_year=? ORDER BY s.position',(year,))]


def available_years():
    years=set()
    for database in SOURCES.values():
        with connect(database) as connection:
            years.update(str(year) for year, in connection.execute('SELECT fiscal_year FROM workbooks'))
    return sorted(years,reverse=True)


def open_appendix_view(parent,center,open_file=None):
    window=tk.Toplevel(parent,show_on_create=False);window.title('부속명세서 조회');center(window,1200,750)
    body=ttk.Frame(window,padding=12);body.pack(fill='both',expand=True)
    toolbar=ttk.Frame(body);toolbar.pack(fill='x',pady=(0,8))
    bar=tk.W.QHBoxLayout(toolbar._q);bar.setContentsMargins(0,0,0,0);bar.setSpacing(8)
    bar.addWidget(tk.W.QLabel('회계연도'),0,tk.C.Qt.AlignmentFlag.AlignVCenter)
    years=available_years();year=tk.StringVar(value=years[0] if years else '')
    year_box=ttk.Combobox(toolbar,textvariable=year,values=years,state='readonly',width=8)
    bar.addWidget(year_box._q,0,tk.C.Qt.AlignmentFlag.AlignVCenter);year_box._q.show();year_box._q.setAccessibleName('부속명세서 회계연도')
    kind=tk.StringVar(value='재무상태표')
    def open_current():
        from qt_ui import messagebox
        index=tabs.currentIndex()
        if index<0:return
        category,name=entries[index]
        try:
            with connect(SOURCES[category]) as connection:
                row=connection.execute('SELECT filename FROM workbooks WHERE fiscal_year=?',(year.get(),)).fetchone()
            if row is None:raise ValueError('선택 연도의 원본 파일이 없습니다.')
            source=DATA/'originals'/Path(row[0]).name
            if not source.is_file():raise FileNotFoundError(source.name)
            if open_file:open_file(source)
            else:
                from app import open_result_file
                open_result_file(source)
        except Exception as error:messagebox.showerror('현재 시트 원본 열기',str(error),parent=window)
    original=tk.W.QPushButton('현재시트열기');original.setAccessibleName('현재시트열기');original.clicked.connect(open_current)
    bar.addWidget(original,0,tk.C.Qt.AlignmentFlag.AlignVCenter);bar.addStretch()
    tab_host=ttk.Frame(body);tab_host.pack(fill='x',pady=(0,8))
    tab_layout=tk.W.QVBoxLayout(tab_host._q);tab_layout.setContentsMargins(0,0,0,0)
    tabs=tk.WorkflowTabBar();tabs.setObjectName('AppendixSheetTabs');tabs.setAccessibleName('부속명세서 시트');tabs.setShape(tk.W.QTabBar.Shape.RoundedNorth)
    tabs.setExpanding(False);tabs.setMinimumWidth(0)
    tabs.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Fixed);tab_layout.addWidget(tabs)
    entries=[(category,name) for category in SOURCES for name in list_sheets(category,year.get())]
    for category,name in entries:
        index=tabs.addTab(name);tabs.setTabToolTip(index,category+' · '+name)
    status=tk.StringVar();ttk.Label(body,textvariable=status).pack(side='bottom',fill='x',pady=(8,0))
    host=ttk.Frame(body);host.pack(fill='both',expand=True)
    layout=tk.W.QVBoxLayout(host._q);layout.setContentsMargins(0,0,0,0)
    view=tk.W.QTableView();layout.addWidget(view)
    model=AppendixModel(window,view);view.setModel(model)
    view.setSortingEnabled(False);view.horizontalHeader().setSectionsClickable(False)
    view.horizontalHeader().setSortIndicatorShown(False);view.horizontalHeader().setStretchLastSection(False)
    view.setEditTriggers(tk.W.QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setAlternatingRowColors(True);view.setShowGrid(True);view.setWordWrap(False)
    view.setTextElideMode(tk.C.Qt.TextElideMode.ElideRight)
    view.setVerticalScrollMode(tk.W.QAbstractItemView.ScrollMode.ScrollPerPixel)
    jobs=Jobs(window,status);jobs.controls=[tab_host,year_box]
    window._appendix_table=view;window._appendix_model=model
    window._appendix_tabs=tabs;window._appendix_sheet_entries=entries
    window._appendix_year=year_box

    def fit(event=None):
        for column,header in enumerate(model.sheet['headers']):
            fit_text=any(label in header for label in ('내용','구분'))
            width=max(120,min(280,tk.G.QFontMetrics(view.font()).horizontalAdvance(header)+24))
            for row in range(model.rowCount()):
                index=model.index(row,column);value=index.data(tk.C.Qt.ItemDataRole.UserRole)
                font=index.data(tk.C.Qt.ItemDataRole.FontRole)
                measured=tk.G.QFontMetrics(font).horizontalAdvance(display_value(value))+20
                width=max(width,measured if fit_text or isinstance(value,(int,float)) else min(280,measured))
            view.setColumnWidth(column,width)
        view.verticalHeader().setDefaultSectionSize(max(28,tk.G.QFontMetrics(view.font()).height()+8))
        view.viewport().update()

    def change_sheet(index):
        if jobs.busy or index<0:return
        category,name=entries[index];kind.set(category);requested_year=year.get()
        def display(sheet):
            view.clearSpans();model.replace(sheet)
            for row,start,span,label in sheet.get('spans',[]):view.setSpan(row,start,1,span)
            fit()
            status.set(f'{requested_year}년 · {category} · {name} · {model.rowCount():,}건')
        jobs.run(lambda:load_sheet(SOURCES[category],name,requested_year),display)
    def change_year(event=None):
        if jobs.busy:return
        entries[:]=[(category,name) for category in SOURCES for name in list_sheets(category,year.get())]
        tabs.blockSignals(True)
        while tabs.count():tabs.removeTab(0)
        for category,name in entries:
            index=tabs.addTab(name);tabs.setTabToolTip(index,category+' · '+name)
        tabs.blockSignals(False)
        view.clearSpans();model.replace({'headers':[],'records':[]})
        if entries:change_sheet(0)
        else:status.set('선택 연도의 자료가 없습니다.')
    year_box.bind('<<ComboboxSelected>>',change_year)
    tabs.currentChanged.connect(change_sheet)
    window.bind('<<ThemeChanged>>',fit)
    window.after(100,lambda:change_sheet(tabs.currentIndex()))
    window.deiconify()
    return window
