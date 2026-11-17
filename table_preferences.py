"""Opt-in column widths, scoped to screen and column schema; never alters table data."""
import hashlib
import json
import qt_ui as q


class ColumnWidths:
    def __init__(self,tree):
        self.tree=tree;self.locked={};self.schema=();self.defaults={};self.loaded=False
        header=tree._q.horizontalHeader();header.setContextMenuPolicy(q.C.Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.menu)
        header.setToolTip('열 경계를 드래그해 너비 조절 · 오른쪽 클릭으로 너비 저장/초기화')
        tree.after(0,self.initialize)
    def identity(self):
        tree=self.tree;parent=tree.master;parts=[]
        while parent is not None:
            if isinstance(parent,q.Window) and not isinstance(parent,q.Tk):parts.append(parent.title())
            if isinstance(parent.master,q.Notebook):
                try:parts.append(parent.master.tab(str(parent),'text'))
                except (KeyError,ValueError,RuntimeError):pass
            parent=parent.master
        # Omit application version: workflow window and schema identify the table.
        return hashlib.sha256(json.dumps([parts,list(tree._columns)],ensure_ascii=False).encode()).hexdigest()
    def store(self):
        root=self.tree._root();launcher=getattr(root,'_launcher',None)
        path=launcher.settings_path.parent/'table-widths.json' if launcher else None
        if not hasattr(root,'_table_width_settings'):
            data={}
            if path:
                try:
                    value=json.loads(path.read_text(encoding='utf-8'))
                    if isinstance(value,dict):data=value
                except (OSError,ValueError):pass
            root._table_width_settings=data
        return root._table_width_settings,path
    def initialize(self):
        if not self.tree.winfo_exists():return
        self.schema=tuple(self.tree._columns)
        self.defaults={c:self.tree.column(c,'width') for c in self.tree._visible_columns()}
        self.loaded=True;data,_=self.store();value=data.get(self.identity(),{})
        if isinstance(value,dict):
            self.locked={c:w for c,w in value.items() if c in self.tree._visible_columns() and type(w) is int and 30<=w<=3000}
            self.apply()
    def width(self,column,requested):
        return self.locked.get(column,requested) if tuple(self.tree._columns)==self.schema else requested
    def apply(self):
        for c,width in self.locked.items():self.tree.column(c,width=width)
    def persist(self):
        data,path=self.store()
        if path:
            try:
                path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp')
                temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(path)
            except OSError as exc:q.messagebox.showwarning('열 너비 저장',str(exc),parent=self.tree)
    def save(self):
        if tuple(self.tree._columns)!=self.schema:self.initialize()
        self.locked={c:max(30,min(3000,self.tree._q.columnWidth(i))) for i,c in enumerate(self.tree._visible_columns())}
        data,_=self.store();data[self.identity()]=dict(self.locked);self.persist()
    def reset(self):
        self.locked={};data,_=self.store();data.pop(self.identity(),None);self.persist()
        for c,width in self.defaults.items():
            if c in self.tree._visible_columns():self.tree.column(c,width=width)
        self.tree._emit('<Configure>',width=self.tree.winfo_width(),height=self.tree.winfo_height())
    def menu(self,point):
        menu=q.W.QMenu(self.tree._q)
        menu.addAction('현재 열 너비 저장',self.save)
        menu.addAction('열 너비 초기화',self.reset)
        menu.exec(self.tree._q.horizontalHeader().mapToGlobal(point))
