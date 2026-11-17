"""학년도별 충원 기초자료. 빈칸은 미수집이며 0명과 구분한다."""
from pathlib import Path
import os
import re
import tempfile
from datetime import date, datetime
from openpyxl import Workbook, load_workbook

COUNTS=('정원내 신입생 모집인원','정원내 신입생 입학인원','학생정원','정원내 재학생 수','정원외 재학생 수')
FIELDS=('대학 유형','집계 범위','기준일',*COUNTS,'자료 출처','비고')


def data_path(folder,year):
    if not re.fullmatch(r'20\d{2}',str(year)):raise ValueError('학년도는 2000~2099년으로 입력하세요.')
    return Path(folder)/f'{year}회계연도'/f'{year}학년도_충원자료.xlsx'


def validate(values):
    result={key:'' if values.get(key) is None else str(values.get(key,'')).strip() for key in FIELDS}
    for key in COUNTS:
        value=result[key]
        if value=='':result[key]=None;continue
        if not re.fullmatch(r'\d+',value):raise ValueError(f'{key}: 0 이상의 정수 또는 빈칸을 입력하세요.')
        result[key]=int(value)
    if result['기준일']:
        try:date.fromisoformat(result['기준일'])
        except ValueError:raise ValueError('기준일은 YYYY-MM-DD 형식으로 입력하세요.')
    return result


def load(folder,year):
    path=data_path(folder,year)
    if not path.exists():return validate({})
    book=load_workbook(path,read_only=True,data_only=False)
    try:
        sheet=book['충원자료'];rows=list(sheet.iter_rows(values_only=True))
        if rows[0][:2]!=('학년도',str(year)):raise ValueError('충원자료의 학년도가 파일명과 다릅니다.')
        values={row[0]:row[1] for row in rows[2:] if row and row[0] in FIELDS}
        if set(values)!=set(FIELDS):raise ValueError('충원자료 항목이 누락되었습니다. 입력폼에서 저장한 양식을 사용하세요.')
        if isinstance(values['기준일'],(date,datetime)):values['기준일']=values['기준일'].strftime('%Y-%m-%d')
        return validate(values)
    finally:book.close()


def save(folder,year,values):
    values=validate(values);path=data_path(folder,year);path.parent.mkdir(parents=True,exist_ok=True)
    book=Workbook();sheet=book.active;sheet.title='충원자료'
    sheet.append(['학년도',str(year)]);sheet.append(['항목','값 (빈칸은 미수집)'])
    for key in FIELDS:
        sheet.append([key,values[key]])
        if isinstance(values[key],str):sheet.cell(sheet.max_row,2).data_type='s'
    sheet.column_dimensions['A'].width=30;sheet.column_dimensions['B'].width=65
    sheet.freeze_panes='B3'
    from openpyxl.styles import PatternFill,Font
    for cell in sheet[2]:cell.fill=PatternFill('solid',fgColor='244C70');cell.font=Font(color='FFFFFF',bold=True)
    fd,temp=tempfile.mkstemp(suffix='.xlsx',dir=path.parent);os.close(fd)
    try:book.save(temp);os.replace(temp,path)
    finally:
        book.close()
        if os.path.exists(temp):os.unlink(temp)
    return path


def open_form(parent,folder,center):
    import qt_ui as tk
    from qt_ui import ttk,messagebox
    from ui_theme import dark_titlebar
    from statement_catalog import discover_years
    window=tk.Toplevel(parent);window.title('충원 자료 입력');dark_titlebar(window);center(window,660,650)
    body=ttk.Frame(window,padding=18);body.pack(fill='both',expand=True);body.columnconfigure(1,weight=1)
    year=tk.StringVar();variables={key:tk.StringVar() for key in FIELDS};active=[None]
    ttk.Label(body,text='학년도').grid(row=0,column=0,sticky='w')
    try:years=list(discover_years(folder))
    except ValueError as e:messagebox.showerror('연도 확인',str(e),parent=window);window.destroy();return
    if not years:years=[str(date.today().year-(date.today().month<3))]
    selector=ttk.Combobox(body,textvariable=year,values=years,state='readonly',width=10);selector.grid(row=0,column=1,sticky='w');year.set(years[0])
    ttk.Label(body,text='미수집 값은 빈칸으로 두세요. 0은 실제 인원이 0명일 때만 입력합니다.\n기준일: YYYY-MM-DD · 집계 범위에 본교/분교 등 포함 범위를 적어 주세요.',style='Muted.TLabel').grid(row=1,column=0,columnspan=2,sticky='w',pady=12)
    for row,key in enumerate(FIELDS,2):
        ttk.Label(body,text=key).grid(row=row,column=0,sticky='w',pady=7,padx=(0,15))
        ttk.Entry(body,textvariable=variables[key]).grid(row=row,column=1,sticky='ew',pady=7)
    status=tk.StringVar();ttk.Label(body,textvariable=status,wraplength=610,style='Muted.TLabel').grid(row=13,column=0,columnspan=2,sticky='w',pady=12)
    baseline=[{}]
    def values():return {key:var.get() for key,var in variables.items()}
    def refresh(event=None):
        if active[0] and values()!=baseline[0]:
            if not messagebox.askyesno('학년도 변경','저장하지 않은 내용을 버리고 다른 학년도를 불러올까요?',parent=window):year.set(active[0]);return
        try:record=load(folder,year.get())
        except Exception as e:
            messagebox.showerror('충원자료 읽기',str(e),parent=window)
            if active[0]:year.set(active[0])
            return
        for key,var in variables.items():var.set('' if record[key] is None else str(record[key]))
        active[0]=year.get();baseline[0]=values();status.set('입력 후 저장하면 해당 연도 폴더에 충원자료 Excel이 생성됩니다.')
    def store():
        if active[0]!=year.get():return
        try:path=save(folder,year.get(),values())
        except Exception as e:messagebox.showerror('저장 실패',str(e),parent=window);return
        baseline[0]=values();status.set(f'저장 완료: {path}')
    def close():
        if values()!=baseline[0] and not messagebox.askyesno('닫기','저장하지 않은 내용을 버리고 닫을까요?',parent=window):return
        window.destroy()
    ttk.Button(body,text='충원자료 Excel 저장',command=store).grid(row=12,column=1,sticky='e',pady=12)
    selector.bind('<<ComboboxSelected>>',refresh);window.protocol('WM_DELETE_WINDOW',close);refresh()
