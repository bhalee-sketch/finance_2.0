"""Pointer-local tooltips for Canvas charts, clamped to the visible viewport."""
from statement_catalog import amount_text


def amount_detail(year,subject,value):
    from analysis_charts import compact
    return f'{year} · {subject}\n{compact(value)} ({amount_text(value)}원)'


def show_tip(canvas,event,text):
    canvas.delete('tip')
    left=canvas.canvasx(0);top=canvas.canvasy(0)
    width=canvas.winfo_width();height=canvas.winfo_height()
    # Leave room for the visible cursor, including its tail and the tip padding.
    gap_x=32;gap_y=36
    x=canvas.canvasx(event.x)+gap_x;y=canvas.canvasy(event.y)+gap_y
    item=canvas.create_text(x,y,text=text,anchor='nw',justify='left',
                            fill='#EDF2FA',font=('맑은 고딕',9),tags='tip',state='disabled')
    bounds=canvas.bbox(item)
    if not isinstance(bounds,(tuple,list)) or len(bounds)!=4:return
    max_width=max(1,width-24)
    if bounds[2]-bounds[0]>max_width:
        canvas.itemconfigure(item,width=max_width)
        bounds=canvas.bbox(item)
    tw=bounds[2]-bounds[0];th=bounds[3]-bounds[1]
    if x+tw+8>left+width:x=max(left+8,canvas.canvasx(event.x)-tw-gap_x)
    if y+th+8>top+height:y=max(top+8,canvas.canvasy(event.y)-th-gap_y)
    canvas.coords(item,x,y);bounds=canvas.bbox(item)
    canvas.create_rectangle(bounds[0]-6,bounds[1]-4,bounds[2]+6,bounds[3]+4,fill='#172231',outline='#637B98',tags='tip',state='disabled')
    canvas.tag_raise(item)


def bind_tip(canvas,item,text):
    def show(event):show_tip(canvas,event,text)
    canvas.tag_bind(item,'<Enter>',show);canvas.tag_bind(item,'<Motion>',show)
    canvas.tag_bind(item,'<Leave>',lambda event:canvas.delete('tip'))


def pie_hover(canvas,cx,cy,radius,inner,slices,total):
    import math
    from analysis_charts import compact
    def move(event):
        if not canvas.find_withtag('slice0'):canvas.delete('tip');return
        x=canvas.canvasx(event.x)-cx;y=cy-canvas.canvasy(event.y)
        if not inner<=math.hypot(x,y)<=radius:canvas.delete('tip');return
        angle=(math.degrees(math.atan2(y,x))-90)%360;start=0
        for label,value in slices:
            extent=float(value/total*360)
            if start<=angle<start+extent:
                show_tip(canvas,event,f'{label}\n{compact(value)} · {value/total*100:.2f}%\n{amount_text(value)}원');return
            start+=extent
        canvas.delete('tip')
    move_id=canvas.bind('<Motion>',move,add='+')
    leave_id=canvas.bind('<Leave>',lambda event:canvas.delete('tip'),add='+')
    base=getattr(canvas,'canvas',canvas)
    # Real Canvas only; chart recorder doubles do not retain widget bindings.
    import qt_ui as tk
    if isinstance(base,tk.Misc):base._chart_hover_bindings=[('<Motion>',move_id),('<Leave>',leave_id)]
