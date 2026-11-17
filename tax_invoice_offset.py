"""첨부 TaxInvoiceFilePicker의 취소/수정 상계 규칙. 원본은 읽기만 한다."""
from collections import defaultdict,deque
import re
from decimal import Decimal,InvalidOperation,ROUND_HALF_EVEN
from itertools import combinations
from pathlib import Path
from openpyxl import Workbook,load_workbook
from finance_data import append_row,format_sheet,save_atomic
from verifier import open_legacy_workbook

ALIASES=(('사업자번호','사업자등록번호'),('품목','품명'),('공급가액',),('세액','부가세액','부가가치세'),('합계금액','합계액','합계'),('분류',))


def text(value):
    if value is None:return ''
    if isinstance(value,float) and value.is_integer():value=int(value)
    return str(value).replace('\t',' ').replace('\xa0',' ').strip()


def header(rows):
    for i,row in enumerate(rows[:20]):
        names=[text(v).replace(' ','').casefold() for v in row];cols=[]
        for aliases in ALIASES:
            found=next((j for j,v in enumerate(names) if v in aliases),None)
            if found is None:break
            cols.append(found)
        if len(cols)==6:return i,cols
    return None


def amount(value):
    if value is None or isinstance(value,bool):return None
    s=text(value).replace(',','').replace('₩','').replace('￦','').replace('원','').replace(' ','')
    if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1]
    try:
        number=Decimal(s)
        if not number.is_finite():return None
        result=number.quantize(Decimal('.0001'),rounding=ROUND_HALF_EVEN)
        return result if Decimal('-922337203685477.5808')<=result<=Decimal('922337203685477.5807') else None
    except InvalidOperation:return None


def load_source(path):
    path=Path(path)
    if path.suffix.lower()=='.xls':
        book=open_legacy_workbook(path)
        try:
            for sheet in book.sheets():
                preview=[sheet.row_values(i) for i in range(min(20,sheet.nrows))]
                match=header(preview)
                if match is not None:
                    import xlrd
                    rows=[]
                    for i in range(sheet.nrows):
                        row=[]
                        for cell in sheet.row(i):
                            if cell.ctype==xlrd.XL_CELL_DATE:value=xlrd.xldate_as_datetime(cell.value,book.datemode)
                            elif cell.ctype==xlrd.XL_CELL_ERROR:value=xlrd.error_text_from_code.get(cell.value,'#ERROR')
                            else:value=cell.value
                            row.append(value)
                        rows.append(row)
                    return rows,*match
        finally:book.release_resources()
    elif path.suffix.lower() in ('.xlsx','.xlsm'):
        book=load_workbook(path,read_only=True,data_only=True,keep_links=False)
        try:
            for sheet in book:
                preview=list(sheet.iter_rows(max_row=20,values_only=True));match=header(preview)
                if match is not None:
                    rows=[list(r) for r in sheet.iter_rows(values_only=True)]
                    while rows and all(v is None for v in rows[-1]):rows.pop()
                    return rows,*match
        finally:book.close()
    else:raise ValueError('xls, xlsx, xlsm 파일을 선택하세요.')
    raise ValueError('첫 20행에서 사업자번호·품목·공급가액·세액·합계금액·분류 열을 가진 시트를 찾지 못했습니다.')


def offset_rows(rows,cols,contexts=None):
    business,item,cs,ct,cg,kind=cols
    groups=defaultdict(list);values={};modified={};removed=set();counts={'1:1 상계 쌍':0,'3건 상계 조합':0,'잔여 그룹 일괄 상계':0,'상계 판정 불가 행':0,'3건 탐색 생략 그룹':0,'0원 제외':0,'품목 변경 수정 상계 쌍':0}
    for i,row in enumerate(rows):
        cell=lambda c:row[c] if c<len(row) else None
        biz=text(cell(business)).replace('-','').replace(' ','').casefold();name=re.sub(r'\s+','',text(cell(item))).casefold()
        numbers=tuple(amount(cell(c)) for c in (cs,ct,cg))
        if all(v==0 for v in numbers):removed.add(i);counts['0원 제외']+=1;continue
        if not biz or not name or any(v is None for v in numbers):counts['상계 판정 불가 행']+=1;continue
        values[i]=numbers;modified[i]='일반(수정)' in text(cell(kind)).casefold();groups[biz,name].append(i)
    for group in groups.values():
        for include_modified in (False,True):
            buckets=defaultdict(deque)
            for i in group:
                if i not in removed and (include_modified or not modified[i]):buckets[values[i]].append(i)
            for i in group:
                if i in removed or (not include_modified and modified[i]) or not any(values[i]):continue
                opposite=tuple(-v for v in values[i]);queue=buckets[opposite]
                while queue and (queue[0]<=i or queue[0] in removed):queue.popleft()
                if queue:
                    j=queue.popleft();removed.update((i,j));counts['1:1 상계 쌍']+=1
        if 3<=len(group)<=60:
            while True:
                found=None
                for include_modified in (False,True):
                    candidates=[i for i in group if i not in removed and (include_modified or not modified[i])]
                    for trio in combinations(candidates,3):
                        if all(sum(values[i][c] for i in trio)==0 for c in range(3)):
                            signs=[values[i][c] for i in trio for c in (0,2)]
                            if any(v>0 for v in signs) and any(v<0 for v in signs):found=trio;break
                    if found:break
                if not found:break
                removed.update(found);counts['3건 상계 조합']+=1
        elif len(group)>60:counts['3건 탐색 생략 그룹']+=1
        remaining=[i for i in group if i not in removed];signs=[v for i in remaining for v in values[i]]
        if len(remaining)>=2 and any(v>0 for v in signs) and any(v<0 for v in signs) and all(sum(values[i][c] for i in remaining)==0 for c in range(3)):
            removed.update(remaining);counts['잔여 그룹 일괄 상계']+=1
    if contexts is not None:
        residual=defaultdict(list)
        for i,numbers in values.items():
            if i not in removed and contexts[i] is not None:
                biz=text(rows[i][business]).replace('-','').replace(' ','').casefold()
                residual[(biz,contexts[i],numbers)].append(i)
        for (biz,context,numbers),indices in list(residual.items()):
            opposite=residual.get((biz,context,tuple(-v for v in numbers)),[])
            if len(indices)==len(opposite)==1:
                i,j=indices[0],opposite[0]
                if i!=j and i not in removed and j not in removed and (modified[i] or modified[j]):
                    removed.update((i,j));counts['품목 변경 수정 상계 쌍']+=1
    return removed,counts


def generate(source,target):
    source=Path(source);target=Path(target)
    if source.resolve()==target.resolve():raise ValueError('원본 파일과 다른 이름으로 저장하세요.')
    if target.suffix.lower()!='.xlsx':raise ValueError('결과는 .xlsx 파일로 저장하세요.')
    rows,head,cols=load_source(source);data=rows[head+1:]
    if not data:raise ValueError('머리글 아래 원자료 행이 없습니다.')
    names=[text(v).replace(' ','') for v in rows[head]]
    context_columns=[names.index(n) for n in ('작성일자','매입/출','계산서종류') if n in names]
    contexts=[tuple(text(row[c]) for c in context_columns) if all(c<len(row) and text(row[c]) for c in context_columns) else None for row in data] if len(context_columns)==3 else None
    removed,counts=offset_rows(data,cols,contexts)
    wb=Workbook();wb.remove(wb.active)
    for title,chosen in [('원자료',range(len(data))),('미처리결과',[i for i in range(len(data)) if i not in removed]),('상계제외',sorted(removed))]:
        ws=wb.create_sheet(title)
        for row in rows[:head+1]:append_row(ws,row)
        chosen=list(chosen)
        for i in chosen:
            row=list(data[i])
            for c in cols[2:5]:
                if c<len(row) and amount(row[c]) is not None:row[c]=amount(row[c])
            append_row(ws,row)
        last_data=ws.max_row
        totals=['']*ws.max_column;totals[0]='합계'
        for c in cols[2:5]:
            totals[c]=sum((amount(data[i][c]) for i in chosen if c<len(data[i]) and amount(data[i][c]) is not None),Decimal(0))
        append_row(ws,totals)
        for c in cols[2:5]:
            for cells in ws.iter_rows(min_row=head+2,min_col=c+1,max_col=c+1):cells[0].number_format='#,##0.####;[Red]-#,##0.####;0'

        format_sheet(ws);ws.freeze_panes=f'A{head+2}';ws.auto_filter.ref=f'A{head+1}:{ws.cell(last_data,ws.max_column).coordinate}'
        from copy import copy
        for c in ws[head+1]:
            c.font=copy(ws.cell(1,c.column).font);c.fill=copy(ws.cell(1,c.column).fill)
    summary=wb.create_sheet('처리요약')
    for row in [('항목','내용'),('원본',str(source)),('원본 행 수',len(data)),('미처리 잔여',len(data)-len(removed)),('상계 제외',len(removed)),*counts.items(),('기준','사업자번호·공백 정규화 품목별 세 금액 상계. 품목 변경은 사업자·작성일·매입/출·계산서종류가 같고 유일한 수정 취소 쌍만 추가 상계. 0원 제외.'),('참고','판정 불가 행은 미처리결과에 유지됩니다. 원본 서식/매크로/수식 대신 읽은 셀 값을 저장합니다.')]:append_row(summary,row)
    format_sheet(summary);wb.active=1
    return save_atomic(wb,target)


def open_picker(parent,initialdir,center,open_file):
    from qt_ui import ttk,filedialog,messagebox
    from finance_ui import shell,saved
    window,body,status,jobs=shell(parent,'세금계산서 미처리 상계',center)
    center(window,740,300)
    ttk.Label(body,text='취소·수정 내역 상계',style='Section.TLabel').pack(anchor='w')
    ttk.Label(body,text='원본 Excel을 선택하면 원자료·미처리결과·상계제외를 새 파일로 저장합니다.\n공백 차이·유일한 수정 취소 쌍을 포함해 상계하고 0원 행을 제외합니다.',wraplength=680).pack(anchor='w',pady=12)
    def execute():
        source=filedialog.askopenfilename(parent=window,initialdir=initialdir,title='상계할 원본 Excel 선택',filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
        if not source:return
        from result_paths import result_path
        target=result_path('세금계산서 미처리 상계')
        if not target:return
        if Path(source).resolve()==Path(target).resolve():messagebox.showerror('저장 위치','원본과 다른 파일 이름을 지정하세요.',parent=window);return
        jobs.run(lambda:generate(source,target),lambda p:saved(window,status,open_file,p))
    status.set('원본은 유지하며, 결과는 새 xlsx 파일로 저장한 뒤 자동으로 엽니다.')
    button=ttk.Button(body,text='원본 파일 선택 · 미처리 상계',command=execute,style='Primary.TButton');button.pack(fill='x',pady=8);jobs.controls.append(button)
