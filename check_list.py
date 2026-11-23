"""검색 가능한 체크박스 복수 선택 목록. Ctrl/Shift 조합 없이 선택한다."""
import qt_ui as tk
from qt_ui import ttk

class CheckList(ttk.Frame):
    def __init__(self,parent,**kwargs):
        height=kwargs.pop('height',8);width=kwargs.pop('width',30)
        super().__init__(parent)
        self.items=[];self.variables=[];self.buttons=[]
        self.search=tk.StringVar()
        entry=ttk.Entry(self,textvariable=self.search);entry.pack(fill='x',pady=(0,4))
        self.canvas=tk.Canvas(self,bg='#192131',highlightthickness=0,width=width*7,height=height*28)
        self.canvas.pack(fill='both',expand=True)
        self.inner=ttk.Frame(self.canvas);self.inner_id=self.canvas.create_window(0,0,window=self.inner,anchor='nw')
        self.inner.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.inner_id,width=e.width))
        self.search.trace_add('write',lambda *_:self.filter())
    def configure(self,cnf=None,**kwargs):
        if 'yscrollcommand' in kwargs:self.canvas.configure(yscrollcommand=kwargs.pop('yscrollcommand'))
        if kwargs or cnf:return super().configure(cnf,**kwargs)
    config=configure
    def yview(self,*args):return self.canvas.yview(*args)
    def filter(self):
        query=self.search.get().strip().casefold()
        for text,button in zip(self.items,self.buttons):
            button.pack_forget()
            if query in text.casefold():button.pack(fill='x',anchor='w')
    def insert(self,index,text):
        self.items.append(str(text));variable=tk.BooleanVar(value=False);self.variables.append(variable)
        button=ttk.Checkbutton(self.inner,text=text,variable=variable,command=lambda:self.event_generate('<<ListboxSelect>>'))
        self.buttons.append(button);self.filter()
    def delete(self,first,last=None):
        for button in self.buttons:button.destroy()
        self.items=[];self.variables=[];self.buttons=[]
    def curselection(self):return tuple(i for i,v in enumerate(self.variables) if v.get())
    def get(self,index):return self.items[int(index)]
    def selection_set(self,first,last=None):self._select(first,last,True)
    def selection_clear(self,first,last=None):self._select(first,last,False)
    def _select(self,first,last,value):
        end=len(self.items)-1 if last=='end' else int(last) if last is not None else int(first)
        for i in range(int(first),end+1):
            if 0<=i<len(self.variables):self.variables[i].set(value)


class CenteredCheckDelegate(tk.W.QStyledItemDelegate):
    """Draw a native checkbox over the table's regular row background."""
    def __init__(self,view):
        super().__init__(view)
        self.checkbox=tk.W.QCheckBox(view)
        self.checkbox.hide()

    def paint(self,painter,option,index):
        cell=tk.W.QStyleOptionViewItem(option)
        self.initStyleOption(cell,index)
        checked=cell.text=='☑'
        cell.text=''
        option.widget.style().drawControl(tk.W.QStyle.ControlElement.CE_ItemViewItem,cell,painter,option.widget)

        indicator=tk.W.QStyleOptionButton()
        indicator.initFrom(self.checkbox)
        indicator.state|=tk.W.QStyle.StateFlag.State_On if checked else tk.W.QStyle.StateFlag.State_Off
        size=18
        indicator.rect=tk.C.QRect(0,0,size,size)
        indicator.rect.moveCenter(option.rect.center())
        self.checkbox.style().drawPrimitive(tk.W.QStyle.PrimitiveElement.PE_IndicatorCheckBox,indicator,painter,self.checkbox)


def tree_checks(tree,default=False,*,centered=False):
    """목록의 체크 열. 행 강조와 별개로 복수 작업 대상을 고른다."""
    chosen=set();original_insert=tree.insert
    tree.configure(show='tree headings',selectmode='browse')
    tree.heading('#0',text='선택');tree.column('#0',width=48,minwidth=48,stretch=False,anchor='center' if centered else 'w')
    if centered:tree._q.setItemDelegateForColumn(0,CenteredCheckDelegate(tree._q))
    def insert(*args,**kwargs):
        kwargs['text']='☑' if default else '☐'
        iid=original_insert(*args,**kwargs)
        if default:chosen.add(iid)
        else:chosen.discard(iid)
        return iid
    tree.insert=insert
    def toggle(event):
        if tree.identify_column(event.x)!='#0':return
        iid=tree.identify_row(event.y)
        if not iid:return
        if iid in chosen:chosen.remove(iid)
        else:chosen.add(iid)
        tree.item(iid,text='☑' if iid in chosen else '☐')
        return 'break'
    tree.bind('<Button-1>',toggle,add='+')
    def selected():return [iid for iid in tree.get_children() if iid in chosen]
    def set_checked(iid,value):
        if value:chosen.add(iid)
        else:chosen.discard(iid)
        tree.item(iid,text='☑' if value else '☐')
    selected.set_checked=set_checked
    return selected
