"""Register explicit department equivalence or scoped counterparty exceptions."""
from copy import deepcopy
from suspense_store import add_alias


def register_exception(settings,kind,source,target,department,approver,reason,start='',end='',purpose=''):
    if kind not in ('department','counterparty_exception'):raise ValueError('예외 유형을 선택하세요.')
    if not all(str(v).strip() for v in (source,target,approver,reason)):raise ValueError('원본·대응 명칭과 등록자·근거를 입력하세요.')
    source,target=source.strip(),target.strip()
    if source==target:raise ValueError('서로 다른 명칭을 입력하세요.')
    updated=deepcopy(settings)
    if kind=='department':
        mappings={rule['source']:rule['target'] for rule in updated.get('aliases',[]) if rule.get('kind')=='department' and rule.get('approved')}
        if source in mappings:raise ValueError('이미 등록된 부서입니다.')
        if target in mappings or source in mappings.values():raise ValueError('부서 규칙이 연쇄 또는 순환 연결되지 않도록 대표 부서 하나로 등록하세요.')
    rule=add_alias(updated,source,target,department.strip() if kind!='department' else '부서 동일 취급',
                   start.strip() or '0001-01-01',end.strip() or '9999-12-31',purpose.strip(),approver.strip(),reason.strip())
    rule['kind']=kind
    return updated


def open_registration(parent,settings,on_save,center):
    import qt_ui as tk
    from qt_ui import ttk,messagebox
    dialog=tk.Toplevel(parent,show_on_create=False);dialog.title('예외규칙 등록');dialog.transient(parent)
    center(dialog,650,540)
    panel=ttk.Frame(dialog,padding=18);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='예외규칙 등록',style='Section.TLabel').pack(anchor='w',pady=(0,8))
    ttk.Label(panel,text='다음 정산검증부터 적용됩니다. 기존 매칭은 유지합니다.').pack(anchor='w',pady=(0,8))
    form=ttk.Frame(panel);form.pack(fill='both',expand=True);form.columnconfigure(1,weight=1)
    kind=tk.StringVar(value='부서 동일 취급')
    box=ttk.Combobox(form,textvariable=kind,values=['부서 동일 취급','거래처 예외'],state='readonly');box.grid(row=0,column=1,sticky='ew',pady=4)
    ttk.Label(form,text='유형').grid(row=0,column=0,sticky='w')
    variables={};scoped=[]
    for row,label in enumerate(['원본 명칭','대응 명칭','적용 부서','시작일 (선택)','종료일 (선택)','목적 (선택)','등록자','근거'],1):
        var=tk.StringVar();variables[label]=var
        caption=ttk.Label(form,text=label);caption.grid(row=row,column=0,sticky='w',padx=(0,12),pady=4)
        entry=ttk.Entry(form,textvariable=var,width=35);entry.grid(row=row,column=1,sticky='ew',pady=4);entry._q.setAccessibleName(label)
        if 3<=row<=6:scoped.append((caption,entry))
    def change(event=None):
        for pair in scoped:
            for widget in pair:widget._q.setVisible(kind.get()=='거래처 예외')
    box.bind('<<ComboboxSelected>>',change);change()
    def save():
        try:
            v={key:value.get() for key,value in variables.items()}
            updated=register_exception(settings,'department' if kind.get()=='부서 동일 취급' else 'counterparty_exception',
                v['원본 명칭'],v['대응 명칭'],v['적용 부서'],v['등록자'],v['근거'],
                v['시작일 (선택)'] if kind.get()=='거래처 예외' else '',v['종료일 (선택)'] if kind.get()=='거래처 예외' else '',v['목적 (선택)'])
            on_save(updated)
        except (ValueError,OSError) as exc:messagebox.showerror('규칙 확인',str(exc),parent=dialog);return
        dialog.destroy()
    buttons=ttk.Frame(panel);buttons.pack(fill='x',pady=(12,0))
    ttk.Button(buttons,text='등록',command=save,style='Primary.TButton').pack(side='right')
    ttk.Button(buttons,text='취소',command=dialog.destroy).pack(side='right',padx=8)
    dialog.deiconify();dialog.grab_set()
    return dialog
