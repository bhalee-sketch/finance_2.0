"""재무 분석, 보조원장 조회 및 Excel 통합 창."""
from pathlib import Path
from numeric_tree import NumericTreeview
import qt_ui as tk
from qt_ui import ttk, filedialog, messagebox
from decimal import Decimal
from datetime import datetime
from statement_ui import Jobs, table
from statement_catalog import amount_text, discover_years
from finance_data import (LEDGER_COLUMNS, load_ledger, filter_ledger, ledger_summary,
                          export_ledger, merge_excel)
from ui_theme import dark_titlebar

FILETYPES=[('Excel','*.xls *.xlsx *.xlsm')]


def shell(parent,title,center,show_status=True):
    window=tk.Toplevel(parent);window.title(title);dark_titlebar(window)
    center(window,1180,min(800,window.winfo_screenheight()-90))
    body=ttk.Frame(window,padding=12);body.pack(fill='both',expand=True)
    status=tk.StringVar(value='자료를 선택하세요.');jobs=Jobs(window,status)
    if show_status:ttk.Label(body,textvariable=status,style='Muted.TLabel',wraplength=1100).pack(side='bottom',fill='x',pady=(8,0))
    return window,body,status,jobs


def saved(window,status,open_file,path):
    status.set(f'저장 완료: {path}')
    try:open_file(path)
    except Exception as e:messagebox.showwarning('저장 완료 · 열기 실패',f'{path}\n{e}',parent=window)


def target_file(window,folder,name):
    # 기존 호출 인터페이스 유지, 저장 위치 선택 없이 공통 결과 폴더 사용.
    from result_paths import result_path
    return result_path(name.removesuffix('.xlsx'))


def fill(tree,headers,rows,numeric=()):
    tree.delete(*tree.get_children());columns=[str(i) for i in range(len(headers))];tree.configure(columns=columns)
    for i,h in enumerate(headers):
        tree.heading(str(i),text=h);tree.column(str(i),width=290 if i==0 else 155,minwidth=70,anchor='e' if i in numeric else 'w')
    for row in rows:tree.insert('','end',values=[amount_text(v) if isinstance(v,(int,float,Decimal)) else ('—' if v is None else v) for v in row])


def content_widths(tree,headers,rows):
    """표 제목과 현재 조회 결과 전체의 표시 문자열을 픽셀로 측정한다."""
    from qt_ui import font as tkfont
    font=tkfont.Font(font=ttk.Style(tree).lookup('Treeview','font') or ('맑은 고딕',10))
    bold=tkfont.Font(font=font);bold.configure(weight='bold')
    from appearance import controller
    from numeric_tree import numeric_cell
    appearance=controller(tree)
    number=tkfont.Font(font=font);number_bold=tkfont.Font(font=bold)
    if appearance:
        number.configure(family=appearance.numeric_family or appearance.family)
        number_bold.configure(family=appearance.numeric_family or appearance.family)
    cache={}
    def measure(value,heading=''):
        value=amount_text(value) if isinstance(value,(int,float,Decimal)) else str(value if value is not None else '—')
        numeric=numeric_cell(heading,value);key=(value,numeric)
        pair=(number,number_bold) if numeric else (font,bold)
        if key not in cache:cache[key]=max(f.measure(value) for f in pair)
        return cache[key]
    widths=[max(45,measure(h)+24) for h in headers]
    for row in rows:
        for i,value in enumerate(row):widths[i]=max(widths[i],measure(value,headers[i])+24)
    return widths


def apply_widths(tree,widths):
    for i,width in enumerate(widths):tree.column(str(i),width=width,minwidth=width,stretch=False)


def compact_combo(box,values):
    """필요한 텍스트 폭만 확보하고 부모 폭에 맞춰 늘리지 않는다."""
    box.configure(values=values)
    widget=box._q
    metrics=widget.fontMetrics()
    pixels=max((metrics.horizontalAdvance(str(value)) for value in values),default=metrics.horizontalAdvance('전체'))
    option=tk.W.QStyleOptionComboBox()
    widget.initStyleOption(option)
    edit=widget.style().subControlRect(tk.W.QStyle.ComplexControl.CC_ComboBox,option,
                                     tk.W.QStyle.SubControl.SC_ComboBoxEditField,widget)
    # Account for the arrow, borders and horizontal padding in the active theme.
    widget.setMinimumWidth(max(70,pixels+max(36,widget.width()-edit.width())+6))



def open_merge(parent,desktop,center,open_file,ledger=False):
    title='원장통합' if ledger else '재무제표 Excel 통합'
    window,body,status,jobs=shell(parent,title,center);sources=[]
    ttk.Label(body,text='동일한 첫 행 헤더 아래 모든 파일의 데이터를 한 시트에 연결합니다.' if ledger else
              '각 파일의 첫 번째 시트를 파일명으로 된 별도 시트에 통합합니다.',style='Section.TLabel').pack(anchor='w',pady=8)
    ttk.Label(body,text='원본은 변경하지 않습니다. XLS · XLSX · XLSM 지원 · 수식은 저장된 계산값을 가져옵니다.',style='Muted.TLabel').pack(anchor='w')
    bar=ttk.Frame(body);bar.pack(fill='x',pady=12)
    tree=table(body,['파일','위치'])
    from check_list import tree_checks
    checked_files=tree_checks(tree,default=True)
    def render():
        old={i:Path(tree.item(i,'values')[1])/tree.item(i,'values')[0] for i in tree.get_children()}
        checked={old[i] for i in checked_files()}
        tree.delete(*tree.get_children())
        for i,p in enumerate(sources):
            iid=tree.insert('','end',iid=str(i),values=[p.name,str(p.parent)])
            checked_files.set_checked(iid,p not in old.values() or p in checked)
        status.set(f'{len(sources)}개 파일 · 선택 순서대로 통합' if ledger else f'{len(sources)}개 파일 · 회계단위 / 재무제표 구분 순으로 통합')
    def add():
        names=filedialog.askopenfilenames(parent=window,initialdir=str(desktop()/'settings'),filetypes=FILETYPES)
        add_paths(names)
    def add_paths(names):
        if jobs.busy:return
        from file_drop import excel_paths
        valid,rejected=excel_paths(names,sources)
        sources.extend(valid)
        render()
        if rejected:messagebox.showwarning('파일 확인','Excel 파일(.xls/.xlsx/.xlsm)만 추가할 수 있습니다.\n'+'\n'.join(rejected),parent=window)
    if ledger:
        drop=ttk.Label(bar,text='Excel 파일을 이 창으로 끌어 놓으세요.',style='Accent.TLabel');drop.pack(side='right',padx=10)
        def dropped(event):
            if jobs.busy:return 'none'
            try:add_paths(window.tk.splitlist(event.data))
            except (tk.TclError,ValueError) as e:messagebox.showerror('파일 추가',str(e),parent=window)
            return 'copy'
        try:
            DND_FILES='DND_Files'
            for widget in (window,tree,drop):
                widget.drop_target_register(DND_FILES);widget.dnd_bind('<<Drop>>',dropped)
        except (ImportError,AttributeError,tk.TclError):
            drop.configure(text='파일 추가 사용 · 드래그 지원은 최신 실행 파일로 재실행하세요.')
    def remove():
        for i in sorted([int(i) for i in checked_files()],reverse=True):sources.pop(i)
        render()
    def execute():
        if not sources:messagebox.showinfo(title,'통합할 파일을 추가하세요.',parent=window);return
        target=target_file(window,sources[0].parent,'원장통합' if ledger else '재무제표 Excel 통합')
        if not target:return
        selected=[sources[int(i)] for i in checked_files()]
        if not selected:messagebox.showinfo(title,'통합할 파일에 체크하세요.',parent=window);return
        def done(result):
            saved(window,status,open_file,result[0]);status.set(f'{len(selected)}개 파일 · 데이터 {result[1]:,}행 통합 완료: {result[0]}')
        jobs.run(lambda:merge_excel(selected,target,ledger),done)
    for label,command in [('파일 추가',add),('체크 파일 제거',remove),('통합 · 저장',execute)]:
        button=ttk.Button(bar,text=label,command=command);button.pack(side='left',padx=(0,8));jobs.controls.append(button)
    tree.column('파일',width=380);tree.column('위치',width=650)


def open_other_tasks(parent,desktop,center,open_file):
    from analysis_runtime import load_analysis_history
    from subprocess import SubprocessError
    from cash_account_filter import filter_cash_accounts
    from result_paths import result_path

    window,body,status,jobs=shell(parent,'기타작업',center)
    ttk.Label(body,text='자금계산서 계정 추출',style='Section.TLabel').pack(anchor='w')
    ttk.Label(body,text='원장 첫 시트에서 자금계산서 계정에 해당하는 행을 추출합니다. 교육외수입은 제외합니다.').pack(anchor='w',pady=6)
    bar=ttk.Frame(body)
    bar.pack(fill='x',pady=8)
    result=None

    def choose():
        nonlocal result
        filename=filedialog.askopenfilename(parent=window,title='원장 엑셀 업로드',filetypes=FILETYPES)
        if not filename:
            return
        source=Path(filename)
        result=None
        launch.configure(state='disabled')
        def work():
            history,_,_=load_analysis_history(desktop()/'settings'/'finance statement',materialize_sources=False)
            return filter_cash_accounts(source,result_path('자금계산서 계정 추출'),history)
        def done(output):
            nonlocal result
            result,scanned,kept=output
            launch.configure(state='normal')
            status.set(f'{source.name} · 전체 {scanned:,}행 · 추출 {kept:,}행 · 제외 {scanned-kept:,}행\n저장 위치 · {result}')
        jobs.run(work,done)

    def launch_result():
        try:
            open_file(result)
        except (OSError, SubprocessError) as error:
            messagebox.showerror('엑셀 열기', str(error), parent=window)

    upload=ttk.Button(bar,text='원장 엑셀 업로드',command=choose,style='Primary.TButton')
    upload.pack(side='left',padx=(0,8))
    launch=ttk.Button(bar,text='엑셀 열기',command=launch_result,state='disabled')
    launch.pack(side='left')
    jobs.controls.extend((upload,launch))
    return window


def open_ledger(parent,desktop,center,open_file):
    from ledger_view import open_ledger as open_view
    return open_view(parent,desktop,center,open_file)


def open_analysis(parent,desktop,center,open_file):
    from financial_analysis_ui import open_financial_analysis
    return open_financial_analysis(parent,desktop,center,open_file)
