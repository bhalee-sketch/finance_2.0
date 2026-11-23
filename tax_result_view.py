"""Show exception rows from the tax verification workbook, in sheet order."""
from openpyxl import load_workbook
from decimal import Decimal,InvalidOperation
import qt_ui as tk
from qt_ui import ttk
from statement_ui import table
from statement_catalog import amount_text


def read_issue_sheets(path):
    owned=not hasattr(path,'worksheets')
    workbook=load_workbook(path,read_only=True,data_only=True) if owned else path
    try:
        result=[]
        for sheet in workbook:
            stream=sheet.iter_rows(values_only=True)
            headers=list(next(stream,()))
            if '금액검증' not in headers:continue
            verdict=headers.index('금액검증')
            differences=[i for i,h in enumerate(headers) if str(h).endswith('차이')]
            issues=[]
            for row in stream:
                if not any(v is not None for v in row):continue
                def differs(value):
                    if value is None or str(value).strip()=='':return False
                    try:
                        number=Decimal(str(value).replace(',','').strip())
                        return not number.is_finite() or number!=0
                    except InvalidOperation:return True
                if any(differs(row[i]) for i in differences):issues.append(list(row))
            result.append({'name':sheet.title,'headers':headers,'rows':issues})
        return result
    finally:
        if owned:workbook.close()


class TaxResultView:
    def __init__(self,parent):
        self.frame=ttk.Frame(parent);self.frame.pack(fill='both',expand=True)
        self.note=tk.StringVar(value='검증을 실행하면 결과 시트별 차이·확인필요 내역을 표시합니다.')
        ttk.Label(self.frame,textvariable=self.note).pack(anchor='w',pady=(4,6))
        self.tab_host=ttk.Frame(self.frame);self.tab_host.pack(side='bottom',fill='x')
        layout=tk.W.QVBoxLayout(self.tab_host._q);layout.setContentsMargins(0,0,0,0)
        self.tabs=tk.WorkflowTabBar();self.tabs.setExpanding(False)
        self.tabs.setMinimumWidth(0);self.tabs.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Fixed)
        layout.addWidget(self.tabs);self.tabs.currentChanged.connect(self.display)
        self.tree=table(self.frame,[])
        self.tree._q.setSortingEnabled(False);self.tree.proxy.sort(-1)
        self.tree._q.horizontalHeader().setSectionsClickable(False)
        self.tree._q.horizontalHeader().setSortIndicatorShown(False)
        self.tree.tag_configure('review',background='#FDE8E8',foreground='#7F1D1D')
        self.tree._q.setHorizontalScrollBarPolicy(tk.C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree._q.setWordWrap(False)
        self.tree.bind('<Configure>',self.fit_columns,add='+')
        self.sheets=[];self.generation=0;self.current_index=-1

    def clear(self):
        self.generation+=1;self.sheets=[];self.current_index=-1
        self.tabs.blockSignals(True)
        while self.tabs.count():self.tabs.removeTab(0)
        self.tabs.blockSignals(False)
        self.tree.delete(*self.tree.get_children())
        self.note.set('검증 중…')

    def set_results(self,sheets):
        self.clear();self.sheets=sheets
        self.tabs.blockSignals(True)
        for sheet in sheets:
            index=self.tabs.addTab(f'{sheet["name"]} ({len(sheet["rows"]):,})')
            self.tabs.setTabToolTip(index,sheet['name'])
        self.tabs.blockSignals(False)
        self.display(0)

    def fit_columns(self,event=None):
        if not 0<=self.current_index<len(self.sheets):return
        headers=self.sheets[self.current_index]['headers']
        if not headers:return
        available=max(1,self.tree._q.viewport().width())
        weights=[135 if any(word in str(h) for word in ('가액','세액','금액','차이')) else 170 for h in headers]
        widths=[int(available*weight/sum(weights)) for weight in weights];widths[-1]+=available-sum(widths)
        self.tree._width_preferences.locked.clear()
        for column,width in enumerate(widths):self.tree.column(str(column),width=width,minwidth=1,stretch=False)
        header=self.tree._q.horizontalHeader();header.setMinimumSectionSize(1)
        header.setSectionResizeMode(tk.W.QHeaderView.ResizeMode.Fixed)

    def display(self,index):
        self.current_index=index
        self.generation+=1;generation=self.generation
        self.tree.delete(*self.tree.get_children())
        if not 0<=index<len(self.sheets):
            self.note.set('표시할 검증 결과가 없습니다.');return
        sheet=self.sheets[index];columns=[str(i) for i in range(len(sheet['headers']))]
        self.tree.configure(columns=columns)
        numeric_columns=set()
        for index_column,(column,header) in enumerate(zip(columns,sheet['headers'])):
            self.tree.heading(column,text=header)
            numeric=any(word in str(header) for word in ('가액','세액','금액','차이')) and header!='금액검증'
            if numeric:numeric_columns.add(index_column)
            self.tree.column(column,width=135 if numeric else 170,anchor='e' if numeric else 'w',stretch=False)
        self.note.set(f'{sheet["name"]} · 차이·확인필요 {len(sheet["rows"]):,}건' if sheet['rows'] else f'{sheet["name"]} · 차이가 없습니다.')
        def chunk(start=0):
            if generation!=self.generation or not self.frame.winfo_exists():return
            for row in sheet['rows'][start:start+100]:
                values=[amount_text(value) if index_column in numeric_columns else ('' if value is None else str(value))
                        for index_column,value in enumerate(row)]
                self.tree.insert('','end',values=values,tags=('review',))
            if start+100<len(sheet['rows']):self.frame.after(1,lambda:chunk(start+100))
        self.fit_columns()
        chunk()
