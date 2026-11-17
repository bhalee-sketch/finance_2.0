"""Show exception rows from the tax verification workbook, in sheet order."""
from openpyxl import load_workbook
import qt_ui as tk
from qt_ui import ttk
from statement_ui import table
from statement_catalog import amount_text


def read_issue_sheets(path):
    workbook=load_workbook(path,read_only=True,data_only=True)
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
                if row[verdict] in ('차이','확인필요') or row[0] in ('홈택스만','학사만') or any(
                    row[i] not in (None,0,'','0') for i in differences):
                    issues.append(list(row))
            result.append({'name':sheet.title,'headers':headers,'rows':issues})
        return result
    finally:workbook.close()


class TaxResultView:
    def __init__(self,parent):
        self.frame=ttk.Frame(parent);self.frame.pack(fill='both',expand=True)
        self.note=tk.StringVar(value='검증을 실행하면 결과 시트별 차이·확인필요 내역을 표시합니다.')
        ttk.Label(self.frame,textvariable=self.note).pack(anchor='w',pady=(4,6))
        self.tab_host=ttk.Frame(self.frame);self.tab_host.pack(side='bottom',fill='x')
        layout=tk.W.QVBoxLayout(self.tab_host._q);layout.setContentsMargins(0,0,0,0)
        self.tabs=tk.W.QTabBar();self.tabs.setExpanding(False);self.tabs.setUsesScrollButtons(True)
        self.tabs.setMinimumWidth(0);self.tabs.setSizePolicy(tk.W.QSizePolicy.Policy.Ignored,tk.W.QSizePolicy.Policy.Fixed)
        layout.addWidget(self.tabs);self.tabs.currentChanged.connect(self.display)
        self.tree=table(self.frame,[])
        self.tree._q.setSortingEnabled(False);self.tree.proxy.sort(-1)
        self.tree._q.horizontalHeader().setSectionsClickable(False)
        self.tree._q.horizontalHeader().setSortIndicatorShown(False)
        self.tree.tag_configure('review',background='#FDE8E8',foreground='#7F1D1D')
        self.sheets=[];self.generation=0

    def clear(self):
        self.generation+=1;self.sheets=[]
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

    def display(self,index):
        self.generation+=1;generation=self.generation
        self.tree.delete(*self.tree.get_children())
        if not 0<=index<len(self.sheets):
            self.note.set('표시할 검증 결과가 없습니다.');return
        sheet=self.sheets[index];columns=[str(i) for i in range(len(sheet['headers']))]
        self.tree.configure(columns=columns)
        for column,header in zip(columns,sheet['headers']):
            self.tree.heading(column,text=header)
            numeric=any(word in str(header) for word in ('가액','세액','금액','차이')) and header!='금액검증'
            self.tree.column(column,width=135 if numeric else 170,anchor='e' if numeric else 'w',stretch=False)
        self.note.set(f'{sheet["name"]} · 차이·확인필요 {len(sheet["rows"]):,}건' if sheet['rows'] else f'{sheet["name"]} · 차이가 없습니다.')
        def chunk(start=0):
            if generation!=self.generation or not self.frame.winfo_exists():return
            for row in sheet['rows'][start:start+100]:
                values=[amount_text(v) if isinstance(v,(int,float)) else ('' if v is None else str(v)) for v in row]
                self.tree.insert('','end',values=values,tags=('review',))
            if start+100<len(sheet['rows']):self.frame.after(1,lambda:chunk(start+100))
        chunk()
