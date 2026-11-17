"""재무제표 결산액의 연도별 추이. 원장 감사 확인과 독립적으로 실행한다."""
from datetime import datetime
from pathlib import Path
import qt_ui as tk
from qt_ui import ttk,messagebox
from finance_ui import shell,fill,saved,target_file,compact_combo,content_widths,apply_widths
from statement_ui import table
from statement_catalog import amount_text
from audit_review import load_statement_history,AccountOrder,matches,trend_values,export_trends


def open_trends(parent,desktop,center,open_file):
    window,body,status,jobs=shell(parent,'재무분석 · 연도별 추이',center)
    settings=desktop()/'settings';data=None
    bar=ttk.Frame(body);bar.pack(fill='x',pady=(0,8));filters={};boxes={}
    for key in ('회계단위','관','항','목'):
        group=ttk.Frame(bar);group.pack(side='left',padx=(0,10));ttk.Label(group,text=key).pack(anchor='w')
        var=tk.StringVar(value='전체');filters[key]=var
        box=ttk.Combobox(group,textvariable=var,state='readonly',width=5);box.pack();boxes[key]=box;jobs.controls.append(box)
    actions=ttk.Frame(bar);actions.pack(side='right',anchor='n')
    note=tk.StringVar(value='연도별 재무제표를 읽고 있습니다…')
    ttk.Label(body,textvariable=note,style='Muted.TLabel',wraplength=1100).pack(fill='x',pady=5)
    canvas=tk.Canvas(body,bg='#192131',highlightthickness=0,height=300);canvas.pack(fill='both',expand=True)
    tree=table(body,['년도','수입 결산','지출 결산']);tree.configure(height=5)
    def current_filters():return {k:v.get() for k,v in filters.items()}
    def options(changed=None):
        keys=list(filters)
        if changed:
            for key in keys[keys.index(changed)+1:]:filters[key].set('전체')
        candidates=[]
        if data:
            for year in sorted(data['history'],reverse=True):
                for scope,parsed in data['history'][year].items():
                    for item in parsed['items'].values():
                        candidates.append(dict(zip(('관','항','목'),list(item['path'])+['']*3),회계단위='교비'+scope if scope!='전체' else '전체'))
        for index,key in enumerate(keys):
            if key=='회계단위':choices=['전체']+list(dict.fromkeys(r['회계단위'] for r in candidates if r['회계단위']!='전체'))
            elif data is None or (key in ('항','목') and filters[keys[index-1]].get()=='전체'):choices=['전체']
            else:
                subset=[r for r in candidates if matches(r,{k:filters[k].get() for k in keys[:index]})]
                choices=['전체']+data['order'].choices(subset,key)
            if filters[key].get() not in choices:filters[key].set('전체')
            compact_combo(boxes[key],choices)
    def draw(event=None):
        canvas.delete('all')
        if data is None:return
        values,explanation=trend_values(data['history'],current_filters());note.set(explanation)
        headers=['년도','수입 결산','지출 결산'];fill(tree,headers,values,numeric=(1,2))
        apply_widths(tree,content_widths(tree,headers,values))
        amounts=[float(v) for row in values for v in row[1:] if v is not None]
        if not amounts:
            canvas.create_text(20,30,anchor='w',text='선택한 관·항·목에 대응하는 재무제표 결산값이 없습니다.',fill='#EDF2FA');return
        w=max(600,canvas.winfo_width());h=max(240,canvas.winfo_height());low=min(0,min(amounts));high=max([0]+amounts);span=high-low or 1
        x=lambda i:95+i*(w-205)/max(1,len(values)-1)
        y=lambda value:h-42-(float(value)-low)/span*(h-115)
        for i,row in enumerate(values):canvas.create_text(x(i),h-20,text=row[0],fill='#EDF2FA')
        for index,(name,color) in enumerate((('수입','#64DAC7'),('지출','#AC9DE8')),1):
            canvas.create_text(15,15+index*18,text=name+' 결산 (원)',fill=color,anchor='w');previous=None
            for i,row in enumerate(values):
                value=row[index]
                if value is None:previous=None;continue
                point=(x(i),y(value))
                if previous:canvas.create_line(*previous,*point,fill=color,width=2)
                canvas.create_oval(point[0]-4,point[1]-4,point[0]+4,point[1]+4,fill=color,outline='')
                canvas.create_text(point[0],point[1]-12-(index-1)*14,text=amount_text(value),fill=color)
                previous=point
    canvas.bind('<Configure>',draw)
    def changed(key):options(key);draw()
    for key,box in boxes.items():box.bind('<<ComboboxSelected>>',lambda e,k=key:changed(k))
    def refresh():
        nonlocal data
        if jobs.busy:return
        data=None;canvas.delete('all');tree.delete(*tree.get_children())
        def done(result):
            nonlocal data
            history,issues,paths=result;data={'history':history,'order':AccountOrder(history),'issues':issues,'sources':list(paths.values())}
            options();draw();status.set(' / '.join(issues) or f'{len(history)}개 연도 · 과목은 최신 재무제표 순서로 표시합니다.')
        jobs.run(lambda:load_statement_history(settings),done)
    def export():
        if data is None:return
        path=target_file(window,None,'재무분석 연도별 증감')
        if not path:return
        if Path(path).resolve() in {Path(p).resolve() for p in data['sources']}:
            messagebox.showerror('저장 위치','원본과 다른 파일명으로 저장하세요.',parent=window);return
        snapshot=data;chosen=current_filters()
        jobs.run(lambda:export_trends(snapshot['history'],chosen,path,snapshot['sources'],snapshot['issues']),lambda p:saved(window,status,open_file,p))
    def enrollment_form():
        from enrollment import open_form
        open_form(window,settings/'finance statement',center)
    for title,command in [('새로고침',refresh),('충원 자료 입력',enrollment_form),('분석 Excel 저장',export)]:
        button=ttk.Button(actions,text=title,command=command);button.pack(side='left',padx=4);jobs.controls.append(button)
    window.after(100,refresh)
