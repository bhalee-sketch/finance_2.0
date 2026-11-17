"""Residual-only user matching, preserving earlier approved allocations."""
from copy import deepcopy
from suspense_engine import Candidate,validate
from suspense_store import action


def prepare_match(result,settings,amounts,approver,reason,allow_partial=False):
    rows=result['ledger']['rows'];byid={t.row_id:t for t in rows}
    if not amounts:raise ValueError('차변과 대변을 선택하세요.')
    for identity,value in amounts.items():
        if identity not in byid or not byid[identity].side or not isinstance(value,int) or value<=0:
            raise ValueError('선택 거래의 배분액은 양의 정수여야 합니다.')
        if value>sum(result['validation']['residual'][identity]):raise ValueError('배분액이 미매칭 잔여액을 초과합니다.')
    debit=sum(v for i,v in amounts.items() if byid[i].side=='D')
    credit=sum(v for i,v in amounts.items() if byid[i].side=='C')
    if allow_partial and 0<debit<credit:
        remaining=debit;allocated={i:v for i,v in amounts.items() if byid[i].side=='D'}
        for identity in sorted((i for i in amounts if byid[i].side=='C'),key=lambda i:(byid[i].day,byid[i].row,i)):
            value=min(amounts[identity],remaining)
            if value:allocated[identity]=value
            remaining-=value
        amounts=allocated
    if sum(v for i,v in amounts.items() if byid[i].side=='C')!=sum(v for i,v in amounts.items() if byid[i].side=='D'):
        raise ValueError('선택 차변·대변 배분 합계가 같아야 합니다.')
    combined=dict(amounts)
    for group in result['groups']:
        if group.ids&amounts.keys():
            old=dict(group.allocations) if group.allocations else {i:byid[i].value for i in group.ids}
            for identity,value in old.items():combined[identity]=combined.get(identity,0)+value
    cs=tuple(i for i in combined if byid[i].side=='C');ds=tuple(i for i in combined if byid[i].side=='D')
    candidate=Candidate('manual',cs,ds,'사용자 승인',1000,(),'사용자 승인',tuple(combined.items()))
    if not cs or not ds or not validate(rows,[candidate])['ok']:raise ValueError('기존 배분을 포함한 검산에 실패했습니다.')
    updated=deepcopy(settings)
    action(updated,result['ledger'],combined,'approve',approver,reason,combined)
    return updated


def prepare_reassignment(result,settings,group_id,outgoing,incoming):
    """Replace one allocated row with a same-side residual; preserve all other allocations."""
    byid={t.row_id:t for t in result['ledger']['rows']}
    group=next((g for g in result['groups'] if g.id==group_id),None)
    if group is None or outgoing not in group.ids:raise ValueError('교체할 기존 매칭 거래를 선택하세요.')
    if incoming not in byid or incoming in group.ids:raise ValueError('기존 그룹 밖의 미매칭 잔여 거래를 선택하세요.')
    if not byid[incoming].side or byid[outgoing].side!=byid[incoming].side:raise ValueError('차변은 차변으로, 대변은 대변으로 교체하세요.')
    allocations=dict(group.allocations) if group.allocations else {i:byid[i].value for i in group.ids}
    amount=allocations.pop(outgoing)
    if sum(result['validation']['residual'][incoming])<amount:raise ValueError('대체 거래의 잔여액이 기존 배분액보다 적습니다.')
    allocations[incoming]=amount
    # A partially matched incoming row retains its earlier group and allocation.
    replaced=[group]
    for other in result['groups']:
        if other is not group and incoming in other.ids:
            replaced.append(other)
            for identity,value in (dict(other.allocations) if other.allocations else {i:byid[i].value for i in other.ids}).items():
                allocations[identity]=allocations.get(identity,0)+value
    candidate=Candidate('replacement',tuple(i for i in allocations if byid[i].side=='C'),tuple(i for i in allocations if byid[i].side=='D'),'수동 재배정',1000,(),'사용자 승인',tuple(allocations.items()))
    untouched=[g for g in result['groups'] if all(g is not old for old in replaced)]
    if not validate(result['ledger']['rows'],untouched+[candidate])['ok']:raise ValueError('교체 후 배분액 검산에 실패했습니다.')
    updated=deepcopy(settings)
    record=action(updated,result['ledger'],allocations,'approve','사용자 직접 재배정','미매칭 거래로 기존 매칭 거래 교체',allocations,blocked=[g.id for g in replaced])
    record['reassignment']={'outgoing':outgoing,'incoming':incoming,'amount':amount,'groups':[g.id for g in replaced]}
    return updated


def apply_manual_match(result,updated):
    """Apply only the user's new allocation; never regenerate automatic candidates."""
    record=updated['actions'][-1]
    if record['action']!='approve' or record['file_hash']!=result['ledger']['hash']:raise ValueError('선택한 원장의 매칭 정보가 아닙니다.')
    rows=result['ledger']['rows'];byid={t.row_id:t for t in rows};ids=set(record['rows'])
    allocations=record['allocations']
    partial=any(allocations[i]<byid[i].value for i in ids)
    group=Candidate('U'+record['id'],tuple(i for i in ids if byid[i].side=='C'),tuple(i for i in ids if byid[i].side=='D'),
                    '수동 재배정' if record.get('reassignment') else '부분정산' if partial else '사용자 매칭',1000,('사용자 선택 매칭·자동 재검증 미실행',),'사용자 승인',tuple(allocations.items()))
    kept=[g for g in result['groups'] if not g.ids&ids];groups=kept+[group]
    validation=validate(rows,groups)
    if not validation['ok']:raise ValueError('수동 매칭 금액 검산에 실패했습니다.')
    output=dict(result,groups=groups,validation=validation,settings=updated)
    output['history']=result.get('history',[])+[('사용자 매칭',','.join(sorted(ids)),group.kind)]
    output['search_status']={g.id:result.get('search_status',{}).get(g.id,'선택 완료') for g in kept}
    output['search_status'][group.id]=group.kind
    output['suggestions']=[c for c in result.get('suggestions',[]) if not c.ids&ids]
    return output


def open_match(parent,result,settings,center,on_save,preselected=()):
    import qt_ui as tk
    from qt_ui import ttk,messagebox
    from statement_ui import table
    from ui_theme import dark_titlebar
    dialog=tk.Toplevel(parent,show_on_create=False);dialog.title('매칭하기');dialog.transient(parent);dark_titlebar(dialog)
    screen=parent._q.screen().availableGeometry()
    center(dialog,min(1180,screen.width()-40),min(680,screen.height()-60))
    outer=ttk.Frame(dialog,padding=12);outer.pack(fill='both',expand=True)
    toolbar=ttk.Frame(outer);toolbar.pack(fill='x',pady=(0,8))
    ttk.Label(toolbar,text='매칭하기',style='Section.TLabel').pack(side='left')
    byid={t.row_id:t for t in result['ledger']['rows']};selected=set(preselected);amounts={};trees={}
    totals=tk.StringVar()
    def update():
        debit=sum(amounts[i] for i in selected if byid[i].side=='D')
        credit=sum(amounts[i] for i in selected if byid[i].side=='C')
        totals.set(f'선택 차변 잔액 {debit:,}원  |  선택 대변 잔액 {credit:,}원  |  매칭 후 잔액 {credit-debit:,}원')
        save_button.configure(state='normal' if 0<debit<=credit else 'disabled')
    def save():
        try:updated=prepare_match(result,settings,{i:amounts[i] for i in selected},'사용자 직접 매칭','선택한 잔액으로 매칭',allow_partial=True)
        except ValueError as exc:messagebox.showerror('매칭 확인',str(exc),parent=dialog);return
        if on_save(updated) is not False:dialog.destroy()
    save_button=ttk.Button(toolbar,text='매칭하기',command=save,style='Primary.TButton');save_button.pack(side='right')
    ttk.Button(toolbar,text='취소',command=dialog.destroy).pack(side='right',padx=8)
    ttk.Label(outer,textvariable=totals).pack(fill='x',pady=(0,6))
    panels=ttk.Panedwindow(outer,orient='horizontal');panels.pack(fill='both',expand=True)
    for side,title in [('D','차변 · 정산 내역'),('C','대변 · 입금 내역')]:
        frame=ttk.Frame(panels);panels.add(frame,weight=1);ttk.Label(frame,text=title).pack(anchor='w',pady=(0,5))
        tree=table(frame,('선택','회계일자','부서','거래선','잔액'),horizontal_scroll=False);trees[side]=tree
        tree._q.setSortingEnabled(False);tree.proxy.sort(-1)
        tree._q.horizontalHeader().setSectionsClickable(False);tree._q.horizontalHeader().setSortIndicatorShown(False)
        tree._q.setWordWrap(False)
        tree._q.setProperty('compactRows',True)
        tree._q.setHorizontalScrollBarPolicy(tk.C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for t in sorted(byid.values(),key=lambda t:(t.day,t.row)):
            residual=sum(result['validation']['residual'][t.row_id])
            if t.side!=side or residual<=0:continue
            amounts[t.row_id]=residual
            tree.insert('','end',iid=t.row_id,values=('',t.day.isoformat(),t.department,t.counterparty,f'{residual:,}'))
        def fit(event=None,t=tree):
            available=max(1,t._q.viewport().width())
            weights=(.09,.23,.23,.23,.22)
            widths=[int(available*w) for w in weights];widths[-1]+=available-sum(widths)
            for col,width in zip(t['columns'],widths):t.column(col,width=width,minwidth=1,stretch=False,anchor='e' if col=='잔액' else 'w')
            t._q.verticalHeader().setDefaultSectionSize(max(28,tk.G.QFontMetrics(t._q.font()).height()+6))
        tree.bind('<Configure>',fit,add='+');tree.after_idle(fit)
        for identity in tree.get_children():
            row=tree.model.rows.index(identity)
            index=tree.proxy.mapFromSource(tree.model.index(row,0))
            holder=tk.W.QWidget();layout=tk.W.QHBoxLayout(holder);layout.setContentsMargins(0,0,0,0)
            check=tk.W.QCheckBox();check.setAccessibleName('거래 선택 '+identity)
            check.setStyleSheet('QCheckBox::indicator {width:22px;height:22px;}')
            check.setChecked(identity in selected);layout.addWidget(check,0,tk.C.Qt.AlignmentFlag.AlignCenter)
            def toggle(checked,identity=identity):
                selected.add(identity) if checked else selected.discard(identity)
                update()
            check.toggled.connect(toggle);tree._q.setIndexWidget(index,holder)
    selected.intersection_update(amounts)
    dialog._match_trees=trees
    dialog._match_totals=totals
    update();dialog.deiconify();dialog.grab_set()
    return dialog


def open_reassignment(parent,result,settings,center,on_save,preselected=()):
    """Choose the incoming residual and outgoing matched row, preview then save."""
    import qt_ui as tk
    from qt_ui import ttk,messagebox
    from statement_ui import table
    from ui_theme import dark_titlebar
    dialog=tk.Toplevel(parent);dialog.title('매칭 건 교체 · 수동 재배정');dialog.transient(parent)
    dark_titlebar(dialog);center(dialog,1250,750)
    outer=ttk.Frame(dialog,padding=12);outer.pack(fill='both',expand=True)
    ttk.Label(outer,text='왼쪽에서 새로 연결할 잔여 거래, 오른쪽에서 대신 뺄 기존 매칭 거래를 선택하세요. 같은 차변/대변끼리 교체합니다.').pack(anchor='w')
    query=tk.StringVar();bar=ttk.Frame(outer);bar.pack(fill='x',pady=6)
    ttk.Label(bar,text='부서·거래선·적요 검색').pack(side='left');entry=ttk.Entry(bar,textvariable=query,width=35);entry.pack(side='left',padx=6)
    panes=ttk.Panedwindow(outer,orient='horizontal');panes.pack(fill='both',expand=True)
    trees={};byid={t.row_id:t for t in result['ledger']['rows']};chosen={};matched={}
    for key,title in (('incoming','새로 연결할 미매칭 잔여'),('outgoing','교체할 기존 매칭 거래')):
        frame=ttk.Frame(panes);panes.add(frame,weight=1);ttk.Label(frame,text=title).pack(anchor='w')
        tree=table(frame,('원본행','구분','회계일자','부서','거래선','적요','금액','매칭번호'));trees[key]=tree
        tree.configure(selectmode='browse')
        for c in tree['columns']:tree.column(c,width=100,stretch=False)
        tree.column('원본행',width=60,anchor='center');tree.column('구분',width=55,anchor='center');tree.column('적요',width=260);tree.column('금액',width=130,anchor='e')
    preview=tk.StringVar(value='양쪽 거래를 선택하면 교체 전후 내역이 표시됩니다.')
    ttk.Label(outer,textvariable=preview,wraplength=1180,justify='left').pack(fill='x',pady=10)
    def update(event=None):
        incoming=trees['incoming'].selection();outgoing=trees['outgoing'].selection()
        if not incoming or not outgoing:
            chosen.clear();save.configure(state='disabled');return
        new=incoming[0];group,old=matched[outgoing[0]]
        try:updated=prepare_reassignment(result,settings,group.id,old,new)
        except ValueError as exc:
            chosen.clear();preview.set(str(exc));save.configure(state='disabled');return
        amount=updated['actions'][-1]['reassignment']['amount'];chosen['settings']=updated
        others=[f'{byid[i].row}행 {byid[i].counterparty}' for i in ordered_ids(group.ids-{old})]
        preview.set(f'교체 전: {byid[old].row}행 {byid[old].counterparty} → 교체 후: {byid[new].row}행 {byid[new].counterparty} ({amount:,}원)\n'
                    f'유지할 연결 상대: {", ".join(others)}\n{byid[old].row}행은 {amount:,}원이 잔여로 돌아갑니다. 다른 매칭은 재검증하지 않습니다.')
        save.configure(state='normal')
    def ordered_ids(ids):return sorted(ids,key=lambda i:(byid[i].day,byid[i].row))
    def populate(event=None):
        chosen.clear();matched.clear()
        for tree in trees.values():tree.delete(*tree.get_children())
        needle=query.get().strip().casefold()
        def passes(t):return needle in f'{t.department} {t.counterparty} {t.description} {t.row}'.casefold()
        def values(t,amount,group=''):return (t.row,'차변' if t.side=='D' else '대변',t.day.isoformat(),t.department,t.counterparty,t.description,f'{amount:,}',group)
        for t in sorted(byid.values(),key=lambda t:(t.day,t.row)):
            residual=sum(result['validation']['residual'][t.row_id])
            if t.side and residual>0 and passes(t):trees['incoming'].insert('','end',iid=t.row_id,values=values(t,residual))
        for group in result['groups']:
            allocations=dict(group.allocations) if group.allocations else {i:byid[i].value for i in group.ids}
            # A search hit keeps the entire matching group visible.
            if not any(passes(byid[i]) for i in group.ids):continue
            for identity in ordered_ids(group.ids):
                key=str(len(matched));matched[key]=(group,identity)
                trees['outgoing'].insert('','end',iid=key,values=values(byid[identity],allocations[identity],group.id))
        save.configure(state='disabled')
    def commit():
        if not chosen:return
        if on_save(chosen['settings']) is not False:dialog.destroy()
    save=ttk.Button(outer,text='교체 저장',command=commit,state='disabled');save.pack(side='right')
    ttk.Button(outer,text='취소',command=dialog.destroy).pack(side='right',padx=8)
    ttk.Button(bar,text='검색',command=populate).pack(side='left');entry.bind('<Return>',populate)
    for tree in trees.values():tree.bind('<<TreeviewSelect>>',update)
    populate()
    for identity in preselected:
        if trees['incoming'].exists(identity):trees['incoming'].selection_set(identity);trees['incoming'].see(identity);break
    dialog.grab_set()
    return dialog
