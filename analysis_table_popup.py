"""내용 크기에 맞춘 분석 금액 표. 화면보다 큰 자료에만 스크롤을 표시한다."""
import qt_ui as tk
from qt_ui import ttk
from statement_ui import table
from ui_theme import dark_titlebar


def amount_popup(parent,headers,rows,display_table,description=''):
    dialog=tk.Toplevel(parent);dialog.title('연도별 금액 · 원');dark_titlebar(dialog)
    panel=ttk.Frame(dialog,padding=10);panel.pack(fill='both',expand=True)
    label=ttk.Label(panel,text=description,style='Accent.TLabel')
    if description:label.pack(anchor='w',pady=(0,8))
    widget=table(panel,headers,auto_scroll=True)
    widget.configure(height=max(1,len(rows)),style='Dashboard.Treeview')
    display_table(widget,headers,rows,range(1,len(headers)))
    widget.tag_configure('total',background='#244C70',foreground='#FFFFFF',font=('맑은 고딕',10,'bold'))
    children=widget.get_children()
    if children:widget.item(children[-1],tags=('total',))
    dialog.update_idletasks()
    width=sum(widget.column(c,'width') for c in widget['columns'])+24
    # Treeview 요청 높이는 실제 테마의 헤더, 테두리, 행 높이를 포함한다.
    height=widget.winfo_reqheight()+20+(label.winfo_reqheight()+8 if description else 0)
    width=max(width,label.winfo_reqwidth()+20 if description else 0)
    width=min(width,parent.winfo_screenwidth()-80);height=min(height,parent.winfo_screenheight()-100)
    x=max(0,parent.winfo_rootx()+(parent.winfo_width()-width)//2)
    y=max(0,parent.winfo_rooty()+(parent.winfo_height()-height)//2)
    dialog.geometry(f'{width}x{height}+{x}+{y}')
    def settle(attempt=0):
        if not dialog.winfo_exists():return
        # Windows 테마/DPI 적용 후 실제 보이는 비율로 부족한 공간을 보정한다.
        first,last=widget.xview();top,bottom=widget.yview()
        extra_w=round(widget.winfo_width()/max(.01,last-first)-widget.winfo_width())+8 if last-first<.999 else 0
        extra_h=round(widget.winfo_height()/max(.01,bottom-top)-widget.winfo_height())+12 if bottom-top<.999 else 0
        w=min(dialog.winfo_width()+extra_w,parent.winfo_screenwidth()-60)
        h=min(dialog.winfo_height()+extra_h,parent.winfo_screenheight()-90)
        if extra_w or extra_h:
            x=max(0,min(dialog.winfo_x(),parent.winfo_screenwidth()-w-20))
            y=max(0,min(dialog.winfo_y(),parent.winfo_screenheight()-h-60))
            dialog.geometry(f'{w}x{h}+{x}+{y}')
            if attempt<3:dialog.after(80,lambda:settle(attempt+1))
        widget.xview_moveto(0);widget.yview_moveto(0)
    dialog.after(100,settle)
    return dialog
