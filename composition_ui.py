"""Independent per-관 composition viewer; no change to the main screen filters."""
import qt_ui as tk
from qt_ui import ttk
from financial_analysis import analysis_rows
from analysis_presentation import pie_values
from analysis_charts import donut
from ui_theme import dark_titlebar


def guan_rows(current,scope,unit,section,guan,depth=1):
    rows,total=analysis_rows(current,None,scope,unit,section,(guan,),None)
    if depth==2:
        children=[]
        for row in rows:
            nested,_=analysis_rows(current,None,scope,unit,section,row['item']['path'],None)
            children.extend(nested or [row])
        rows=children
    return rows,total


def open_guan_composition(parent,current,scope,unit,section,selected,title):
    items=current.get('datasets',{}).get((scope,unit),{}).get('items',{}).values()
    choices=list(dict.fromkeys(item['path'][0] for item in items if item['section']==section and item['path']))
    if not choices:return
    window=tk.Toplevel(parent);window.title('관별 구성비');dark_titlebar(window)
    w=min(1000,window.winfo_screenwidth()-80);h=min(760,window.winfo_screenheight()-100)
    window.geometry(f'{w}x{h}');window.minsize(600,420)
    body=ttk.Frame(window,padding=12);body.pack(fill='both',expand=True)
    controls=ttk.Frame(body);controls.pack(fill='x',pady=(0,6))
    ttk.Label(controls,text=title).pack(side='left',padx=(0,12))
    guan=tk.StringVar(value=selected if selected in choices else choices[0]);depth=tk.IntVar(value=1)
    combo=ttk.Combobox(controls,textvariable=guan,values=choices,state='readonly',width=22);combo.pack(side='left')
    plot=ttk.Frame(body);plot.pack(fill='both',expand=True)
    canvas=tk.Canvas(plot,bg='#192131',highlightthickness=0);canvas.pack(side='left',fill='both',expand=True)
    scrollbar=ttk.Scrollbar(plot,command=canvas.yview)
    def scroll(first,last):
        scrollbar.set(first,last)
        if float(first)<=0 and float(last)>=1:scrollbar.pack_forget()
        else:scrollbar.pack(side='right',fill='y')
    canvas.configure(yscrollcommand=scroll)
    def draw(event=None):
        rows,total=guan_rows(current,scope,unit,section,guan.get(),depth.get())
        donut(canvas,pie_values(rows),source_total=total,total_label=guan.get())
    for value,label in ((1,'항별'),(2,'목별')):
        ttk.Radiobutton(controls,text=label,variable=depth,value=value,command=draw).pack(side='left',padx=6)
    combo.bind('<<ComboboxSelected>>',draw);canvas.bind('<Configure>',draw)
    canvas.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
