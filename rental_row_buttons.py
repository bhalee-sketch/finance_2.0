"""Real per-row PDF buttons positioned over the Treeview action column."""
from qt_ui import ttk


class ContractButtons:
    def __init__(self,tree,command):
        self.tree=tree;self.command=command;self.buttons=[];self.pending=False
        for option in ('xscrollcommand','yscrollcommand'):
            previous=tree.cget(option)
            def scroll(*values,previous=previous):
                if previous:previous(*values)
                self.schedule()
            tree.configure(**{option:scroll})
        for event in ('<Configure>','<Map>','<ButtonRelease-1>','<B1-Motion>'):
            tree.bind(event,lambda e:self.schedule(),add='+')
    def reset(self,records):
        for _,button in self.buttons:button.destroy()
        self.buttons=[]
        for iid,record in zip(self.tree.get_children(),records):
            button=ttk.Button(self.tree,text='계약서 보기',command=lambda r=record:self.command(r),padding=(3,0))
            button._q.setStyleSheet('QPushButton {padding:0 3px;min-height:0;border-radius:4px;}')
            self.buttons.append((iid,button))
        self.schedule()
    def schedule(self):
        if self.pending:return
        self.pending=True;self.tree.after_idle(self.sync)
    def sync(self):
        self.pending=False
        if not self.tree.winfo_exists():return
        for iid,button in self.buttons:
            bounds=self.tree.bbox(iid,'11') if self.tree.exists(iid) else ()
            if not bounds:button.place_forget();continue
            x,y,w,h=bounds
            # Hide partially clipped buttons instead of covering adjacent columns/headings.
            if x<0 or x+w>self.tree._q.viewport().width() or y<0 or h<10:
                button.place_forget();continue
            width=min(w-4,button.winfo_reqwidth(),72)
            height=min(h-4,22)
            button.place(x=x+(w-width)//2,y=y+(h-height)//2,width=width,height=height)
