"""Responsive widths for financial tables and matching Excel exports."""
import math
import unicodedata

MONEY={'금액','정산금액','잔액','차변','대변','배분','차변 잔여','대변 잔여','잔여 건수','순잔액(대변−차변)'}
CENTER={'번호','선택','원본행','구분'}
LONG={'적요','목적·근거','근거','탐색 상태'}


def text_units(value):
    return max((sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1 for ch in line) for line in str(value or '').split('\n')),default=0)


def fit_widths(headers,rows,available,measure):
    """Protect monetary values; share remaining space among wrapping text columns."""
    values=[[] for _ in headers]
    for row in rows:
        for i,value in enumerate(row[:len(headers)]):values[i].append(str(value))
    minimum=[];preferred=[];weight=[]
    for h,items in zip(headers,values):
        longest=sorted(set(items),key=text_units,reverse=True)[:8]
        if h in MONEY:
            needed=max([measure(h,False)]+[measure(v,True) for v in longest])+14
            minimum.append(max(65,needed));preferred.append(max(80,needed));weight.append(.3)
        elif h in CENTER:
            needed=max([measure(h,False)]+[measure(v,False) for v in longest])+12
            minimum.append(max(36,needed));preferred.append(max(40,needed));weight.append(.2)
        else:
            minimum.append(82 if '일자' in h else 95 if h in LONG else 48)
            preferred.append(min(420 if h in LONG else 180,max(minimum[-1],max([measure(h,False)]+[measure(v,False) for v in longest])+14)))
            weight.append(3 if h in LONG else 1.3 if '거래' in h or '부서' in h or '계좌' in h or '예적금' in h else 1)
    target=max(int(available),sum(minimum));widths=list(minimum);space=target-sum(widths)
    while space>0:
        active=[i for i in range(len(widths)) if widths[i]<preferred[i]]
        if not active:active=list(range(len(widths)))
        total=sum(weight[i] for i in active)
        spent=0
        for i in active:
            add=max(1,int(space*weight[i]/total))
            if widths[i]<preferred[i]:add=min(add,preferred[i]-widths[i])
            add=min(add,space-spent);widths[i]+=add;spent+=add
        space-=spent
    return [int(w) for w in widths]


def fit_tree(tree,records):
    """Called after results/size changes, never from every paint or scroll event."""
    from qt_ui import ttk
    columns=list(tree['displaycolumns'])
    if columns==['#all']:columns=list(tree['columns'])
    columns=[tree.column(c,'id') for c in columns]
    all_columns=list(tree['columns']);indexes=[all_columns.index(c) for c in columns]
    if not hasattr(tree,'_column_titles'):tree._column_titles={c:tree.heading(c,'text') for c in all_columns}
    headers=[tree._column_titles[c] for c in columns]
    rows=[[row[i] for i in indexes] for row in records]
    if tree.winfo_width()<100:return
    style=ttk.Style(tree);name=tree.cget('style') or 'Treeview'
    normal=tree._font(style.lookup(name,'font'));numeric=tree._font(style.lookup(name,'font'),True)
    heading_font=tree._font(style.lookup(name+'.Heading','font'))
    from qt_ui import font as tkfont
    bold_number=tkfont.Font(root=tree,font=numeric);bold_number.configure(weight='bold')
    measure=lambda value,is_number:max(numeric.measure(str(value)),bold_number.measure(str(value))) if is_number else normal.measure(str(value))
    widths=fit_widths(headers,rows,tree.winfo_width()-4,measure)
    preferences=getattr(tree,'_width_preferences',None)
    if preferences:widths=[preferences.width(c,w) for c,w in zip(columns,widths)]
    tree._wrap_cells=True
    tree._font_by_name={str(font):font for font in tree._fonts.values()}
    max_lines=1
    for i,(column,width) in enumerate(zip(columns,widths)):
        tree.column(column,width=width,minwidth=20,stretch=False)
        if headers[i] in MONEY:continue
        # Only a few longest candidates need expensive exact font wrapping.
        candidates={str(row[i]) for row in rows}
        for value in candidates:
            max_lines=max(max_lines,len(tree.wrap_text(value,normal,max(1,width-12)).split('\n')))
    unique=getattr(tree,'_fit_style',None)
    if not unique:
        unique='Fit'+str(id(tree))+'.'+name;tree._fit_style=unique
    # A uniform row height is required by Tk's native geometry/selection model.
    # Wrap long descriptions instead of clipping or expanding the total width.
    rowheight=max(30,max_lines*max(normal.metrics('linespace'),numeric.metrics('linespace'))+10)
    style.configure(unique,rowheight=rowheight)
    tree.configure(style=unique)
    for column,width,title in zip(columns,widths,headers):
        tree.heading(column,text=tree.wrap_text(title,heading_font,max(1,width-12)))
    tree.refresh_numbers()


def fit_tree_async(tree,records,done=lambda:None):
    """Warm font metrics in small GUI-thread slices before fitting a large result."""
    import time
    from qt_ui import ttk
    previous=getattr(tree,'_layout_warm_job',None)
    if previous is not None:tree.after_cancel(previous)
    style=ttk.Style(tree);name=tree.cget('style') or 'Treeview'
    font=tree._font(style.lookup(name,'font'))
    tree._font_by_name={str(f):f for f in tree._fonts.values()}
    chars=iter(sorted({char for row in records for value in row for char in str(value)}))
    def warm():
        tree._layout_warm_job=None
        if not tree.winfo_exists():return
        deadline=time.perf_counter()+.006
        while True:
            try:char=next(chars)
            except StopIteration:
                fit_tree(tree,records);done();return
            tree._character_width(str(font),char)
            if time.perf_counter()>=deadline:
                tree._layout_warm_job=tree.after(1,warm);return
    tree._layout_warm_job=tree.after(1,warm)


def format_excel(ws,headers):
    from openpyxl.styles import Alignment,Font
    from openpyxl.utils import get_column_letter
    rows=list(ws.iter_rows(min_row=2,values_only=True))
    # A compact landscape layout, with wrapping instead of extremely wide columns.
    display_rows=[[f'{value:,}' if headers[i] in MONEY and isinstance(value,(int,float)) else value for i,value in enumerate(row)] for row in rows]
    width_pixels=fit_widths(headers,display_rows,1450,lambda value,n:text_units(value)*7)
    widths=[max(5,(w-5)/7) for w in width_pixels]
    for i,width in enumerate(widths,1):ws.column_dimensions[get_column_letter(i)].width=round(width,2)
    for row in ws:
        lines=1
        for i,cell in enumerate(row):
            header=headers[i];center=header in CENTER or cell.row==1
            cell.alignment=Alignment(horizontal='center' if center else 'right' if header in MONEY else 'left',vertical='center',wrap_text=True)
            cell.font=Font(name='맑은 고딕',size=10,bold=cell.row==1)
            usable=max(1,widths[i]-2)
            line_count=sum(max(1,math.ceil(text_units(line)/usable)) for line in str(cell.value if cell.value is not None else '').split('\n'))
            lines=max(lines,line_count)
        ws.row_dimensions[row[0].row].height=min(409,lines*16+8)
    ws.sheet_view.zoomScale=80
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0;ws.print_title_rows='1:1'
    ws.print_options.horizontalCentered=True
