"""Qt widget and event adapters for the existing screen controllers.

No Tcl interpreter or Tk widgets are created. The small declarative interface lets
screen controllers retain their existing business callbacks during the migration.
"""
from __future__ import annotations
from types import SimpleNamespace
import itertools
import re
import sys
import traceback
import weakref
from pathlib import Path
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W
from shiboken6 import isValid

TclError = RuntimeError
END='end'; BOTH='both'; LEFT='left'; RIGHT='right'; TOP='top'; BOTTOM='bottom'; X='x'; Y='y'; NONE='none'; HORIZONTAL='horizontal'; VERTICAL='vertical'; EXTENDED='extended'; MULTIPLE='multiple'; SINGLE='single'; DISABLED='disabled'; NORMAL='normal'
_app=None
_default_root=None
_registry=weakref.WeakValueDictionary()
_variables=weakref.WeakValueDictionary()
_fonts=weakref.WeakValueDictionary()
_named_fonts={}
_ids=itertools.count(1)

def application():
    global _app
    if _app is None:
        _app=W.QApplication.instance() or W.QApplication(sys.argv[:1])
        _app.setApplicationName('Work Space')
        _app.setOrganizationName('WorkSpace')
        icon=Path(__file__).resolve().parent/'assets'/'workspace.ico'
        if icon.is_file():_app.setWindowIcon(G.QIcon(str(icon)))
        _app.setStyle('Fusion')
        _app.setQuitOnLastWindowClosed(False)
    return _app

def qwidget(value):return value._q if isinstance(value,Widget) else value if isinstance(value,W.QWidget) else None

def _flatten(values):
    for value in values:
        if isinstance(value,(tuple,list)):yield from _flatten(value)
        else:yield value

def _cnfmerge(values):
    result={}
    for value in values:
        if value:result.update(value)
    return result

def _invoke(callback,*args):
    try:return callback(*args)
    except Exception:
        typ,value,tb=sys.exc_info()
        if _default_root and _default_root.report_callback_exception:
            _default_root.report_callback_exception(typ,value,tb)
        else:traceback.print_exception(typ,value,tb)

class Variable:
    def __init__(self,master=None,value=None,name=None):
        self.name=name or 'qtvar'+str(next(_ids));self.callbacks={}
        if self.name in _variables:self.__dict__=_variables[self.name].__dict__;return
        self.value=self.convert(value if value is not None else self.default);_variables[self.name]=self
    default=''
    def convert(self,v):return v
    def get(self):return self.value
    def set(self,value):
        value=self.convert(value)
        if self.value==value:return
        self.value=value
        for callback in list(self.callbacks.values()):_invoke(callback,self.name,'','write')
    def trace_add(self,mode,callback):
        token=str(next(_ids));self.callbacks[token]=callback;return token
    def trace_remove(self,mode,token):self.callbacks.pop(token,None)
    def __str__(self):return self.name
class StringVar(Variable):
    def convert(self,v):return '' if v is None else str(v)
class BooleanVar(Variable):
    default=False
    def convert(self,v):return v not in (False,0,'0','','false','False',None)
class IntVar(Variable):
    default=0
    def convert(self,v):return int(float(v or 0))
class DoubleVar(Variable):
    default=0.
    def convert(self,v):return float(v or 0)

class Font:
    def __init__(self,root=None,font=None,name=None,**kw):
        application()
        if isinstance(font,Font):self.q=G.QFont(font.q)
        elif isinstance(font,G.QFont):self.q=G.QFont(font)
        elif isinstance(font,(tuple,list)):
            self.q=G.QFont(str(font[0]),abs(int(font[1])) if len(font)>1 else 10)
            if len(font)>2:self.q.setBold('bold' in str(font[2:]));self.q.setItalic('italic' in str(font[2:]))
        elif str(font) in _fonts:self.q=G.QFont(_fonts[str(font)].q)
        else:self.q=G.QFont(application().font())
        self.name=name or 'qtfont'+str(next(_ids));_fonts[self.name]=self;self.configure(**kw)
    def configure(self,**kw):
        if 'family' in kw:self.q.setFamily(str(kw['family']))
        if 'size' in kw:self.q.setPointSize(max(1,abs(int(kw['size']))))
        if 'weight' in kw:self.q.setBold(kw['weight']=='bold')
        if 'slant' in kw:self.q.setItalic(kw['slant']=='italic')
    config=configure
    def actual(self,option=None):
        values={'family':G.QFontInfo(self.q).family(),'size':self.q.pointSize(),'weight':'bold' if self.q.bold() else 'normal','slant':'italic' if self.q.italic() else 'roman','underline':int(self.q.underline()),'overstrike':int(self.q.strikeOut())}
        return values[option] if option else values
    def measure(self,text):return G.QFontMetrics(self.q).horizontalAdvance(str(text))
    def metrics(self,option=None):
        m=G.QFontMetrics(self.q);values={'linespace':m.lineSpacing(),'ascent':m.ascent(),'descent':m.descent(),'fixed':int(m.font().fixedPitch()) if hasattr(m,'font') else 0}
        return values[option] if option else values
    def __str__(self):return self.name

def families(root=None):application();return G.QFontDatabase.families()
def nametofont(name,root=None):
    if name not in _named_fonts:_named_fonts[name]=Font(name=name)
    return _named_fonts[name]
font=SimpleNamespace(Font=Font,families=families,nametofont=nametofont)

def _margins(value):
    if isinstance(value,(tuple,list)):
        if len(value)==4:return tuple(map(int,value))
        if len(value)==2:return int(value[0]),int(value[1]),int(value[0]),int(value[1])
        value=value[0] if value else 0
    return (int(value or 0),)*4

def _pair(value):return tuple(value) if isinstance(value,(tuple,list)) else (int(value or 0),)*2

class PackLayout(W.QLayout):
    """Side/fill/expand layout, expressed in device-independent Qt coordinates."""
    def __init__(self,parent):
        self._hint_cache=None
        super().__init__(parent);self.entries=[];self.setContentsMargins(0,0,0,0);self.setSpacing(0)
    def invalidate(self):
        self._hint_cache=None
        super().invalidate()
    def addItem(self,item):self.entries.append((item,{}));self.invalidate()
    def add(self,widget,options):
        self.removeWidget(widget);self.addChildWidget(widget);self.entries.append((W.QWidgetItem(widget),options))
        for key,offset in (('before',0),('after',1)):
            target=qwidget(options.get(key))
            if target is not None:
                entry=self.entries.pop();index=next((i for i,(item,_) in enumerate(self.entries) if item.widget() is target),len(self.entries));self.entries.insert(index+offset,entry);break
        self.invalidate()
    def count(self):return len(self.entries)
    def itemAt(self,i):return self.entries[i][0] if 0<=i<len(self.entries) else None
    def takeAt(self,i):
        self._hint_cache=None
        return self.entries.pop(i)[0] if 0<=i<len(self.entries) else None
    def sizeHint(self):return self._size(False)
    def minimumSize(self):return self._size(False)
    def _size(self,minimum):
        if not minimum and self._hint_cache is not None:return C.QSize(self._hint_cache)
        width=height=0
        for item,o in self.entries:
            if item.widget().isHidden():continue
            size=item.minimumSize() if minimum else item.sizeHint();px=_pair(o.get('padx',0));py=_pair(o.get('pady',0))
            w=size.width()+sum(px);h=size.height()+sum(py)
            if o.get('side') in ('left','right'):width+=w;height=max(height,h)
            else:height+=h;width=max(width,w)
        l,t,r,b=self.getContentsMargins();result=C.QSize(width+l+r,height+t+b)
        if not minimum:self._hint_cache=C.QSize(result)
        return result
    def setGeometry(self,rect):
        super().setGeometry(rect);l,t,r,b=self.getContentsMargins();area=rect.adjusted(l,t,-r,-b)
        entries=[e for e in self.entries if not e[0].widget().isHidden()]
        for index,(item,o) in enumerate(entries):
            side=o.get('side','top');horizontal=side in ('left','right');size=item.sizeHint();px=_pair(o.get('padx',0));py=_pair(o.get('pady',0));fill=o.get('fill','none')
            natural=size.width()+sum(px) if horizontal else size.height()+sum(py)
            if o.get('expand'):
                same=[(it,op) for it,op in entries[index:] if (op.get('side','top') in ('left','right'))==horizontal]
                needed=sum((it.sizeHint().width()+sum(_pair(op.get('padx',0))) if horizontal else it.sizeHint().height()+sum(_pair(op.get('pady',0)))) for it,op in same)
                count=sum(bool(op.get('expand')) for _,op in same)
                available=area.width() if horizontal else area.height()
                natural+=max(0,available-needed)//max(1,count)
            natural=max(0,min(natural,area.width() if horizontal else area.height()))
            if side=='left':parcel=C.QRect(area.left(),area.top(),natural,area.height());area.setLeft(area.left()+natural)
            elif side=='right':parcel=C.QRect(area.right()-natural+1,area.top(),natural,area.height());area.setRight(area.right()-natural)
            elif side=='bottom':parcel=C.QRect(area.left(),area.bottom()-natural+1,area.width(),natural);area.setBottom(area.bottom()-natural)
            else:parcel=C.QRect(area.left(),area.top(),area.width(),natural);area.setTop(area.top()+natural)
            parcel.adjust(px[0],py[0],-px[1],-py[1]);w=parcel.width() if fill in ('x','both') else min(size.width(),parcel.width());h=parcel.height() if fill in ('y','both') else min(size.height(),parcel.height())
            anchor=o.get('anchor','center');x=parcel.left() if 'w' in anchor else parcel.right()-w+1 if 'e' in anchor else parcel.center().x()-w//2;y=parcel.top() if 'n' in anchor else parcel.bottom()-h+1 if 's' in anchor else parcel.center().y()-h//2
            item.setGeometry(C.QRect(x,y,max(0,w),max(0,h)))

class EventFilter(C.QObject):
    def __init__(self,owner):super().__init__(owner._q);self.owner=owner
    def eventFilter(self,obj,event):
        w=self.owner;t=event.type();mapping={C.QEvent.Type.Resize:'<Configure>',C.QEvent.Type.Show:'<Map>',C.QEvent.Type.Enter:'<Enter>',C.QEvent.Type.Leave:'<Leave>',C.QEvent.Type.FocusIn:'<FocusIn>',C.QEvent.Type.FocusOut:'<FocusOut>',C.QEvent.Type.Close:'<Close>',C.QEvent.Type.MouseMove:'<Motion>',C.QEvent.Type.Wheel:'<MouseWheel>'}
        if t==C.QEvent.Type.Show and isinstance(w,Window):
            from ui_theme import dark_titlebar
            dark_titlebar(w)
        seq=mapping.get(t);extra={}
        if hasattr(event,'position'):
            pos=event.position();extra.update(x=int(pos.x()),y=int(pos.y()))
        if hasattr(event,'globalPosition'):
            pos=event.globalPosition();extra.update(x_root=int(pos.x()),y_root=int(pos.y()))
        if hasattr(event,'modifiers'):
            mod=event.modifiers();extra['state']=(1 if mod&C.Qt.KeyboardModifier.ShiftModifier else 0)|(4 if mod&C.Qt.KeyboardModifier.ControlModifier else 0)
            if hasattr(event,'buttons') and event.buttons()&C.Qt.MouseButton.LeftButton:extra['state']|=0x100
        if t in (C.QEvent.Type.MouseButtonPress,C.QEvent.Type.MouseButtonRelease,C.QEvent.Type.MouseButtonDblClick):
            num={C.Qt.MouseButton.LeftButton:1,C.Qt.MouseButton.MiddleButton:2,C.Qt.MouseButton.RightButton:3}.get(event.button(),1);extra['num']=num
            seq=f'<Double-{num}>' if t==C.QEvent.Type.MouseButtonDblClick else f'<ButtonPress-{num}>' if t==C.QEvent.Type.MouseButtonPress else f'<ButtonRelease-{num}>'
            if t==C.QEvent.Type.MouseButtonPress and w._emit(f'<Button-{num}>',**extra)=='break':return True
            if t==C.QEvent.Type.MouseButtonPress:w._emit('<ButtonPress>',**extra)
        if t==C.QEvent.Type.Wheel:extra['delta']=event.angleDelta().y()
        if t==C.QEvent.Type.KeyPress:
            keys={C.Qt.Key.Key_Return:'Return',C.Qt.Key.Key_Enter:'Return',C.Qt.Key.Key_Escape:'Escape',C.Qt.Key.Key_Space:'space',C.Qt.Key.Key_Delete:'Delete',C.Qt.Key.Key_Tab:'Tab',C.Qt.Key.Key_Down:'Down',C.Qt.Key.Key_Up:'Up'}
            key=keys.get(event.key(),chr(event.key()).lower() if C.Qt.Key.Key_A<=event.key()<=C.Qt.Key.Key_Z else event.text());extra['keysym']=key;extra['char']=event.text()
            prefix='Control-' if event.modifiers()&C.Qt.KeyboardModifier.ControlModifier else ''
            seq=f'<{prefix}{key}>'
            if w._emit('<KeyPress>',**extra)=='break':return True
        if t==C.QEvent.Type.Close:
            callback=w._protocols.get('WM_DELETE_WINDOW')
            if callback:event.ignore();_invoke(callback);return True
            event.ignore();w.destroy();return True
        if seq:
            if seq=='<Configure>' and isinstance(w,Canvas) and hasattr(w,'scene') and not w._options.get('scrollregion'):
                w.scene.setSceneRect(0,0,max(1,w._q.viewport().width()),max(1,w._q.viewport().height()))
            if seq=='<Configure>':
                for child in list(w.children.values()):
                    if child.winfo_exists() and child._manager=='place':child.place(**child._place_options)
            extra.update(width=w.winfo_width(),height=w.winfo_height())
            if w._emit(seq,**extra)=='break':return True
            if seq=='<Motion>' and extra.get('state',0)&0x100:w._emit('<B1-Motion>',**extra)
        if isinstance(w,Canvas) and t==C.QEvent.Type.MouseMove:w._hover(extra)
        return False

class Widget:
    qt_type=W.QWidget
    def __init__(self,master=None,cnf=None,**kw):
        application();self.master=master if master is not None else _default_root;self.children={};self._options={};self._bindings={};self._protocols={};self._timers={};self._traces=[];self._destroyed=False;self._manager='';self._name='qt'+str(next(_ids));_registry[self._name]=self
        self._q=self.qt_type(self.master._container() if isinstance(self.master,Widget) else qwidget(self.master));self._q.setObjectName(self._name);self._q.setMinimumSize(0,0);self._q.setMouseTracking(True)
        if self.master is not None and isinstance(self.master,Widget):self.master.children[self._name]=self
        self._filter=EventFilter(self);self._q.installEventFilter(self._filter)
        self._q.hide();self.configure(**_cnfmerge((cnf,kw)))
    def __str__(self):return self._name
    def _root(self):
        obj=self
        while isinstance(obj.master,Widget):obj=obj.master
        return obj
    def _container(self):return self._q
    def _layout(self,kind):
        parent=self.master._container();layout=parent.layout()
        if layout is None:layout=PackLayout(parent) if kind=='pack' else W.QGridLayout(parent);layout.setContentsMargins(0,0,0,0)
        return layout
    def pack(self,cnf=None,**kw):
        options=_cnfmerge((cnf,kw)) or getattr(self,'_pack_options',{});self._pack_options=options;self._manager='pack'
        self._q.show();layout=self._layout('pack')
        if isinstance(layout,PackLayout):layout.add(self._q,options)
        else:raise RuntimeError('Cannot mix grid and pack in the same parent')
    def pack_forget(self):
        if self.master and self.master._container().layout():self.master._container().layout().removeWidget(self._q)
        self._q.hide();self._manager=''
    forget=pack_forget
    def pack_info(self):return getattr(self,'_pack_options',{})
    def grid(self,cnf=None,**kw):
        options=_cnfmerge((cnf,kw)) or getattr(self,'_grid_options',{});self._grid_options=options;self._manager='grid';layout=self._layout('grid')
        if not isinstance(layout,W.QGridLayout):raise RuntimeError('Cannot mix pack and grid in the same parent')
        layout.addWidget(self._q,int(options.get('row',0)),int(options.get('column',0)),int(options.get('rowspan',1)),int(options.get('columnspan',1)));layout.setSpacing(6);self._q.show()
    grid_remove=pack_forget
    grid_forget=pack_forget
    def place(self,**kw):
        self._manager='place';self._place_options=kw;parent=self.master._container();w=int(kw.get('width',parent.width()*kw.get('relwidth',0) or self._q.sizeHint().width()));h=int(kw.get('height',parent.height()*kw.get('relheight',0) or self._q.sizeHint().height()));x=int(kw.get('x',0)+parent.width()*kw.get('relx',0));y=int(kw.get('y',0)+parent.height()*kw.get('rely',0));anchor=kw.get('anchor','nw')
        if 'e' in anchor:x-=w
        elif anchor in ('center','n','s'):x-=w//2
        if 's' in anchor:y-=h
        elif anchor in ('center','e','w'):y-=h//2
        self._q.setGeometry(x,y,w,h);self._q.show();self._q.raise_()
    place_forget=pack_forget
    def rowconfigure(self,index,**kw):
        layout=self._container().layout()
        if layout is None:layout=W.QGridLayout(self._container());layout.setContentsMargins(0,0,0,0)
        if isinstance(layout,W.QGridLayout):
            if 'weight' in kw:layout.setRowStretch(int(index),int(kw['weight']))
            if 'minsize' in kw:layout.setRowMinimumHeight(int(index),int(kw['minsize']))
    def columnconfigure(self,index,**kw):
        layout=self._container().layout()
        if layout is None:layout=W.QGridLayout(self._container());layout.setContentsMargins(0,0,0,0)
        if isinstance(layout,W.QGridLayout):
            if 'weight' in kw:layout.setColumnStretch(int(index),int(kw['weight']))
            if 'minsize' in kw:layout.setColumnMinimumWidth(int(index),int(kw['minsize']))
    grid_rowconfigure=rowconfigure;grid_columnconfigure=columnconfigure
    def pack_propagate(self,flag):pass
    grid_propagate=pack_propagate
    def configure(self,cnf=None,**kw):
        if isinstance(cnf,str):return self.cget(cnf)
        options=_cnfmerge((cnf,kw));self._options.update(options)
        for key,value in options.items():
            if key=='state':
                self._q.setEnabled(value!='disabled')
                if isinstance(self._q,W.QLineEdit):self._q.setReadOnly(value=='readonly')
                if isinstance(self._q,W.QComboBox):self._q.setEditable(value!='readonly')
            elif key=='text' and hasattr(self._q,'setText'):self._q.setText(str(value))
            elif key=='textvariable':self._connect_variable(value)
            elif key=='font':self._q.setFont(Font(font=value).q)
            elif key=='width' and isinstance(self,(Entry,Combobox,Spinbox,Label,Button,Listbox)):
                self._q.setMinimumWidth(max(16,round(float(value)*G.QFontMetricsF(self._q.font()).averageCharWidth()+16)))
            elif key=='width' and not isinstance(self,(Entry,Combobox,Spinbox,Label,Button,Listbox,Treeview)):self._q.resize(max(1,int(float(value))),self._q.height())
            elif key=='height' and not isinstance(self,(Text,Listbox,Treeview)):self._q.resize(self._q.width(),max(1,int(float(value))))
            elif key=='wraplength' and isinstance(self._q,W.QLabel):self._q.setWordWrap(bool(value))
            elif key in ('padding','padx','pady'):
                if key=='padding':self._q.setContentsMargins(*_margins(value))
            elif key=='cursor':self._q.setCursor(C.Qt.CursorShape.PointingHandCursor if value=='hand2' else C.Qt.CursorShape.SizeAllCursor if value=='fleur' else C.Qt.CursorShape.ArrowCursor)
            elif key=='values' and isinstance(self._q,W.QComboBox):
                text=str(self._variable.get()) if hasattr(self,'_variable') else self._q.currentText();self._q.blockSignals(True);self._q.clear();self._q.addItems([str(v) for v in value]);self._q.setCurrentIndex(self._q.findText(text));
                if self._q.isEditable():self._q.setEditText(text)
                self._q.blockSignals(False)
            elif key=='image' and value is not None:
                pix=value.pixmap if isinstance(value,PhotoImage) else value
                if isinstance(self._q,W.QAbstractButton):self._q.setIcon(G.QIcon(pix))
                elif isinstance(self._q,W.QLabel):self._q.setPixmap(pix)
        raw={k:v for k,v in self._options.items() if k in ('bg','background','fg','foreground')}
        appearance=getattr(self._root(),'_appearance',None)
        if appearance:
            appearance.widgets[self]=raw.copy()
            raw=appearance.options(raw)
        if raw:
            bg=raw.get('bg',raw.get('background'));fg=raw.get('fg',raw.get('foreground'));palette=self._q.palette()
            if bg:palette.setColor(G.QPalette.ColorRole.Window,G.QColor(bg));palette.setColor(G.QPalette.ColorRole.Base,G.QColor(bg));self._q.setAutoFillBackground(True)
            if fg:palette.setColor(G.QPalette.ColorRole.WindowText,G.QColor(fg));palette.setColor(G.QPalette.ColorRole.Text,G.QColor(fg))
            self._q.setPalette(palette)
            rules=[]
            if bg:rules.append('background-color:'+str(bg))
            if fg:rules.append('color:'+str(fg))
            self._q.setStyleSheet('#'+self._name+' {'+';'.join(rules)+';}')
        self._apply_label_font()
        if 'style' in options:self._q.setProperty('role',str(options['style']));self._q.style().unpolish(self._q);self._q.style().polish(self._q)
        return None
    def _apply_label_font(self):
        if not isinstance(self._q,W.QLabel):return
        appearance=getattr(self._root(),'_appearance',None)
        if not appearance:return
        from numeric_tree import numeric_text
        spec=self._options.get('font',self._q.font());f=Font(font=spec).q
        if not isinstance(spec,Font):f.setFamily((appearance.numeric_family or appearance.family) if numeric_text(self._q.text()) else appearance.family)
        self._q.setFont(f)
    config=configure
    def cget(self,key):
        if key=='background':return self._options.get('background',self._options.get('bg',''))
        if key=='foreground':return self._options.get('foreground',self._options.get('fg',''))
        if key=='state':return 'disabled' if not self._q.isEnabled() else self._options.get(key,'normal')
        if key=='text' and hasattr(self._q,'text'):return self._q.text()
        if key=='width':return self._options.get(key,self._q.width())
        if key=='height':return self._options.get(key,self._q.height())
        return self._options.get(key,'')
    def __getitem__(self,key):return self.cget(key)
    def __setitem__(self,key,value):self.configure(**{key:value})
    def _connect_variable(self,var):
        if not isinstance(var,Variable):var=_variables[str(var)]
        self._variable=var
        def update(*_):
            if not self.winfo_exists():return
            value=var.get();self._q.blockSignals(True)
            if isinstance(self._q,W.QLineEdit):self._q.setText(str(value))
            elif isinstance(self._q,W.QSpinBox):self._q.setValue(int(value or 0))
            elif isinstance(self._q,W.QComboBox):
                index=self._q.findText(str(value))
                if index>=0:self._q.setCurrentIndex(index)
                elif self._q.isEditable():self._q.setEditText(str(value))
                else:self._q.setCurrentIndex(-1)
            elif hasattr(self._q,'setText'):self._q.setText(str(value))
            self._q.blockSignals(False)
            self._apply_label_font()
        self._traces.append((var,var.trace_add('write',update)));update()
        if isinstance(self._q,W.QLineEdit):self._q.textChanged.connect(var.set)
        elif isinstance(self._q,W.QComboBox):self._q.currentTextChanged.connect(var.set)
        elif isinstance(self._q,W.QSpinBox):self._q.valueChanged.connect(var.set)
    def bind(self,sequence,func=None,add=None):
        if func is None:return self._bindings.get(sequence,[])
        token=str(next(_ids))
        if isinstance(self,Window) and sequence in ('<Escape>','<Return>'):
            shortcuts=getattr(self,'_shortcuts',{});self._shortcuts=shortcuts
            if sequence not in shortcuts:
                shortcut=G.QShortcut(G.QKeySequence('Esc' if sequence=='<Escape>' else 'Return'),self._q)
                shortcut.activated.connect(lambda seq=sequence:self._emit(seq));shortcuts[sequence]=shortcut
        if add!='+':self._bindings[sequence]=[]
        self._bindings.setdefault(sequence,[]).append((token,func));return token
    def unbind(self,sequence,funcid=None):
        if funcid:self._bindings[sequence]=[(k,v) for k,v in self._bindings.get(sequence,[]) if k!=funcid]
        else:self._bindings.pop(sequence,None)
    def _emit(self,sequence,**kw):
        if sequence!='<Destroy>' and (self._destroyed or not isValid(self._q)):return
        event=SimpleNamespace(**dict(dict(widget=self,x=0,y=0,x_root=0,y_root=0,state=0,time=int(C.QDateTime.currentMSecsSinceEpoch()),delta=0,width=self.winfo_width(),height=self.winfo_height()),**kw))
        for _,callback in list(self._bindings.get(sequence,[])):
            if _invoke(callback,event)=='break':return 'break'
    def event_generate(self,sequence,**kw):
        if isinstance(self,Canvas) and sequence=='<Motion>':self._hover(kw)
        return self._emit(sequence,**kw)
    def after(self,ms,callback=None,*args):
        if callback is None:return
        timer=C.QTimer(self._q);timer.setSingleShot(True);token=str(next(_ids));self._timers[token]=timer
        def call():
            self._timers.pop(token,None)
            if self.winfo_exists():_invoke(callback,*args)
            timer.deleteLater()
        timer.timeout.connect(call);timer.start(max(0,int(ms)));return token
    def after_idle(self,callback,*args):return self.after(0,callback,*args)
    def after_cancel(self,token):
        timer=self._timers.pop(token,None)
        if timer is not None and isValid(timer):timer.stop();timer.deleteLater()
    def destroy(self):
        if self._destroyed:return
        self._emit('<Destroy>');self._destroyed=True
        self._modal=False
        # Qt removes native modal blocking when a still-modal window is hidden.
        # Changing modality first can leave Windows' owner window blocked.
        self._q.hide()
        if self._q.isWindow():self._q.setWindowModality(C.Qt.WindowModality.NonModal)
        for child in list(self.children.values()):child.destroy()
        for token in list(self._timers):self.after_cancel(token)
        for var,token in self._traces:var.trace_remove('write',token)
        if isinstance(self.master,Widget):self.master.children.pop(self._name,None)
        self._q.hide();self._q.deleteLater()
    def winfo_exists(self):return not self._destroyed and isValid(self._q)
    def winfo_children(self):return list(self.children.values())
    def winfo_width(self):return self._q.width() if isValid(self._q) else 0
    def winfo_height(self):return self._q.height() if isValid(self._q) else 0
    def winfo_reqwidth(self):return max(1,self._q.sizeHint().width())
    def winfo_reqheight(self):return max(1,self._q.sizeHint().height())
    def winfo_screenwidth(self):return application().primaryScreen().availableGeometry().width()
    def winfo_screenheight(self):return application().primaryScreen().availableGeometry().height()
    def winfo_x(self):return self._q.x()
    def winfo_y(self):return self._q.y()
    def winfo_rootx(self):return self._q.mapToGlobal(C.QPoint()).x()
    def winfo_rooty(self):return self._q.mapToGlobal(C.QPoint()).y()
    def winfo_ismapped(self):return self.winfo_exists() and self._q.isVisible()
    def winfo_manager(self):return self._manager
    def winfo_id(self):return int(self._q.winId())
    def winfo_pointerxy(self):p=G.QCursor.pos();return p.x(),p.y()
    def update(self):application().processEvents()
    def update_idletasks(self):
        # Flush geometry/paint requests without running user input or worker timers
        # while a screen controller is still constructing its widgets.
        C.QCoreApplication.sendPostedEvents(None,C.QEvent.Type.LayoutRequest)
        layout=self._q.layout()
        if layout:layout.activate()
        C.QCoreApplication.sendPostedEvents(None,C.QEvent.Type.UpdateRequest)
    def focus_set(self):self._q.setFocus()
    focus_force=focus_set
    def focus_get(self):
        current=application().focusWidget();return next((w for w in _registry.values() if w._q is current),None)
    def clipboard_clear(self):application().clipboard().clear()
    def clipboard_append(self,value):application().clipboard().setText(str(value))
    def getvar(self,name):return _variables[name].get()
    def nametowidget(self,name):return _registry[str(name)]
    def lift(self,*args):self._q.raise_();self._q.activateWindow()
    def lower(self,*args):self._q.lower()
    def grab_set(self):
        self._modal=True;window=self._q.window()
        if window.isVisible() and window.windowModality()==C.Qt.WindowModality.ApplicationModal:return
        # Qt requires hide/show to apply modality changes to a visible window.
        window.hide();window.setWindowModality(C.Qt.WindowModality.ApplicationModal);window.show()
    def grab_release(self):
        self._modal=False;window=self._q.window();visible=window.isVisible()
        window.hide();window.setWindowModality(C.Qt.WindowModality.NonModal)
        if visible:window.show()
    def grab_current(self):
        return next((w for w in reversed(list(_registry.values())) if getattr(w,'_modal',False) and w.winfo_exists() and w._q.isVisible() and w._root() is self._root()),None)
    def wait_variable(self,var):
        loop=C.QEventLoop();token=var.trace_add('write',lambda *_:loop.quit())
        try:loop.exec()
        finally:var.trace_remove('write',token)
    def wait_window(self,window=None):
        window=window or self;loop=C.QEventLoop();window._q.destroyed.connect(loop.quit);loop.exec()
    def drop_target_register(self,*args):
        self._q.setAcceptDrops(True)
        owner=self
        class DropFilter(C.QObject):
            def eventFilter(self,obj,event):
                if event.type()==C.QEvent.Type.DragEnter and event.mimeData().hasUrls():event.acceptProposedAction();return True
                if event.type()==C.QEvent.Type.Drop:
                    paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()];owner._emit('<<Drop>>',data=paths);event.acceptProposedAction();return True
                return False
        self._drop_filter=DropFilter(self._q);self._q.installEventFilter(self._drop_filter)
    def dnd_bind(self,event,callback):return self.bind(event,callback)

class Window(Widget):
    report_callback_exception=None
    def __init__(self,master=None,show_on_create=True,**kw):
        super().__init__(master,**kw)
        self._q.setWindowFlag(C.Qt.WindowType.Window,True)
        self._q.setAttribute(C.Qt.WidgetAttribute.WA_DeleteOnClose,False)
        self._content=W.QWidget();self._content.setObjectName(self._name+'Content')
        self._scroll=W.QScrollArea(self._q);self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(W.QFrame.Shape.NoFrame);self._scroll.setWidget(self._content)
        outer=W.QVBoxLayout(self._q);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0);outer.addWidget(self._scroll)
        self._q.resize(900,650);self.tk=Tcl()
        if show_on_create:self._q.show()
    def _container(self):return self._content
    def winfo_reqwidth(self):return max(1,self._content.sizeHint().width())
    def winfo_reqheight(self):return max(1,self._content.sizeHint().height())
    def title(self,value=None):
        if value is None:return self._q.windowTitle()
        self._q.setWindowTitle(value)
    def geometry(self,value=None):
        if value is None:return f'{self.winfo_width()}x{self.winfo_height()}{self.winfo_x():+d}{self.winfo_y():+d}'
        match=re.fullmatch(r'(?:(\d+)x(\d+))?([+-]\d+)?([+-]\d+)?',str(value))
        if not match:raise ValueError('Invalid geometry: '+str(value))
        w,h,x,y=match.groups()
        if w:self._q.resize(int(w),int(h))
        if x is not None and y is not None:self._q.move(int(x),int(y))
    def minsize(self,w,h):self._q.setMinimumSize(int(w),int(h))
    def resizable(self,x,y):
        self._q.setMaximumSize(16777215 if x else self._q.width(),16777215 if y else self._q.height())
    def protocol(self,name,callback=None):
        if callback is None:return self._protocols.get(name)
        self._protocols[name]=callback
    def transient(self,parent):self._q.setParent(qwidget(parent),C.Qt.WindowType.Window)
    def withdraw(self):self._q.hide()
    def deiconify(self):self._q.showNormal()
    def overrideredirect(self,value):
        visible=self._q.isVisible();self._q.setWindowFlag(C.Qt.WindowType.FramelessWindowHint,bool(value))
        if visible:self._q.show()
    def attributes(self,name,value=None):
        if value is None:return self._q.windowOpacity() if name=='-alpha' else bool(self._q.windowFlags()&C.Qt.WindowType.WindowStaysOnTopHint)
        if name=='-alpha':self._q.setWindowOpacity(float(value))
        elif name=='-topmost':
            if bool(self._q.windowFlags()&C.Qt.WindowType.WindowStaysOnTopHint)==bool(value):return
            visible=self._q.isVisible();self._q.setWindowFlag(C.Qt.WindowType.WindowStaysOnTopHint,bool(value))
            if visible:self._q.show()
        elif name=='-fullscreen':self._q.showFullScreen() if value else self._q.showNormal()
    def option_add(self,*args):pass
    def iconbitmap(self,bitmap=None,default=None):self._q.setWindowIcon(G.QIcon(default or bitmap))
    def iconphoto(self,default,*images):
        if images:self._q.setWindowIcon(G.QIcon(images[0].pixmap))
    def mainloop(self):
        self._in_mainloop=True
        try:return application().exec()
        finally:self._in_mainloop=False
    def quit(self):application().quit()
class Tk(Window):
    def __init__(self,**kw):
        global _default_root
        _default_root=None
        super().__init__(None,**kw);self.master=None;_default_root=self
    def destroy(self):
        if getattr(self,'_in_mainloop',False):application().quit()
        super().destroy()
class Toplevel(Window):pass
class Frame(Widget):pass
class LabelFrame(Widget):
    qt_type=W.QGroupBox
    def configure(self,cnf=None,**kw):
        super().configure(cnf,**kw)
        if 'text' in kw:self._q.setTitle(str(kw['text']))
class Label(Widget):
    qt_type=W.QLabel
    def __init__(self,*args,**kw):super().__init__(*args,**kw);self._q.setTextInteractionFlags(C.Qt.TextInteractionFlag.TextSelectableByMouse);self._q.setWordWrap(bool(kw.get('wraplength')))
class Button(Widget):
    qt_type=W.QPushButton
    def __init__(self,*args,**kw):super().__init__(*args,**kw);self._q.clicked.connect(lambda:_invoke(self._options['command']) if self._options.get('command') else None)
    def invoke(self):
        if self._q.isEnabled() and self._options.get('command'):return _invoke(self._options['command'])
class Entry(Widget):
    qt_type=W.QLineEdit
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw)
        if kw.get('show'):self._q.setEchoMode(W.QLineEdit.EchoMode.Password)
        self._q.setMinimumWidth(65)
    def get(self):return self._q.text()
    def delete(self,first,last=None):self._q.clear()
    def insert(self,index,text):self._q.setText(str(text)) if index==0 else self._q.insert(str(text))
    def selection_range(self,*args):self._q.selectAll()
class DropDownComboBox(W.QComboBox):
    def showPopup(self):
        super().showPopup()
        popup=self.view().window()
        if not popup.isVisible():return
        below=self.mapToGlobal(C.QPoint(0,self.height()))
        screen=self.screen().availableGeometry()
        room=screen.bottom()-below.y()+1
        if room>=40:
            popup.resize(max(self.width(),popup.width()),min(popup.height(),room))
            popup.move(max(screen.left(),min(below.x(),screen.right()-popup.width()+1)),below.y())

class Combobox(Widget):
    qt_type=DropDownComboBox
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw);self._q.setMinimumWidth(70);self._q.setEditable(kw.get('state')!='readonly');self._q.activated.connect(lambda index:self._emit('<<ComboboxSelected>>'))
    def get(self):return self._q.currentText()
    def set(self,value):
        if hasattr(self,'_variable'):self._variable.set(value)
        else:self._q.setCurrentText(str(value))
    def current(self,index=None):
        if index is None:return self._q.currentIndex()
        self._q.setCurrentIndex(int(index))
class Spinbox(Widget):
    qt_type=W.QSpinBox
    def configure(self,cnf=None,**kw):
        self._q.setRange(int(kw.get('from_',self._options.get('from_',-2147483647))),int(kw.get('to',self._options.get('to',2147483647))))
        if 'increment' in kw:self._q.setSingleStep(int(kw['increment']))
        super().configure(cnf,**kw)
        if 'state' in kw:self._q.setReadOnly(kw['state']=='readonly')
    config=configure
    def get(self):return str(self._q.value())
    def set(self,value):self._q.setValue(int(value))
    def delete(self,*args):self._q.clear()
    def insert(self,index,value):self._q.setValue(int(value))
class Checkbutton(Button):
    qt_type=W.QCheckBox
    def __init__(self,*args,**kw):
        var=kw.get('variable') or BooleanVar();kw['variable']=var
        Widget.__init__(self,*args,**kw);self._var=var
        def update(*_):
            self._q.blockSignals(True);self._q.setChecked(var.get()==self._options.get('onvalue',True));self._q.blockSignals(False)
        self._traces.append((var,var.trace_add('write',update)));update()
        self._q.toggled.connect(lambda checked:var.set(self._options.get('onvalue',True) if checked else self._options.get('offvalue',False)))
        self._q.clicked.connect(lambda:_invoke(self._options['command']) if self._options.get('command') else None)
class Radiobutton(Checkbutton):
    qt_type=W.QRadioButton
    def __init__(self,*args,**kw):
        variable=kw.get('variable') or StringVar();kw['variable']=variable;kw['onvalue']=kw.get('value');super().__init__(*args,**kw);self._q.setAutoExclusive(False)
        self._q.toggled.disconnect()
        self._q.toggled.connect(lambda checked:variable.set(self._options['value']) if checked else None)
class Progressbar(Widget):
    qt_type=W.QProgressBar
    def start(self,*args):self._q.setRange(0,0)
    def stop(self):self._q.setRange(0,100);self._q.setValue(100)
class Separator(Widget):
    qt_type=W.QFrame
    def __init__(self,*args,**kw):super().__init__(*args,**kw);self._q.setFrameShape(W.QFrame.Shape.HLine)
class Scrollbar(Widget):
    qt_type=W.QScrollBar
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw);self._q.setOrientation(C.Qt.Orientation.Horizontal if kw.get('orient')=='horizontal' else C.Qt.Orientation.Vertical);self._q.setRange(0,1000);self._q.valueChanged.connect(lambda v:_invoke(self._options['command'],'moveto',v/1000) if self._options.get('command') else None)
        command=kw.get('command');owner=getattr(command,'__self__',None);axis=getattr(command,'__name__','')
        if isinstance(owner,Widget) and isinstance(owner._q,W.QAbstractScrollArea):
            if axis=='xview':owner._q.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            elif axis=='yview':owner._q.setVerticalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    def set(self,first,last):self._q.blockSignals(True);self._q.setValue(round(float(first)*1000));self._q.setPageStep(max(1,round((float(last)-float(first))*1000)));self._q.blockSignals(False)
class Scale(Widget):
    qt_type=W.QSlider
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw);self._q.setOrientation(C.Qt.Orientation.Horizontal);self._q.setRange(int(kw.get('from_',0)),int(kw.get('to',100)))
        var=kw.get('variable')
        if var:
            self._q.setValue(int(var.get()));self._q.valueChanged.connect(var.set);self._traces.append((var,var.trace_add('write',lambda *_:self._q.setValue(int(var.get())))))
        self._q.valueChanged.connect(lambda v:_invoke(kw['command'],v) if kw.get('command') else None)
    def set(self,value):self._q.setValue(int(float(value)))
    def get(self):return self._q.value()

class Notebook(Widget):
    qt_type=W.QTabWidget
    def __init__(self,*args,**kw):super().__init__(*args,**kw);self._tabs=[];self._q.currentChanged.connect(lambda i:self._emit('<<NotebookTabChanged>>'))
    def add(self,child,**kw):
        child._manager='notebook'
        if child not in self._tabs:self._tabs.append(child);self._q.addTab(child._q,str(kw.get('text','')));child._q.show()
    def tabs(self):return tuple(str(c) for c in self._tabs if c.winfo_exists() and self._q.indexOf(c._q)>=0)
    def select(self,tab=None):
        if tab is None:return str(self._tabs_by_index(self._q.currentIndex()))
        self._q.setCurrentWidget(qwidget(_registry.get(str(tab),tab)) if not isinstance(tab,int) else self._q.widget(tab))
    def _tabs_by_index(self,i):return next((c for c in self._tabs if c._q is self._q.widget(i)),None)
    def tab(self,tab,option=None,**kw):
        child=_registry.get(str(tab),tab);i=self._q.indexOf(qwidget(child)) if not isinstance(tab,int) else tab
        if 'text' in kw:self._q.setTabText(i,str(kw['text']))
        if 'state' in kw:self._q.setTabEnabled(i,kw['state']!='disabled')
        return self._q.tabText(i) if option=='text' else {'text':self._q.tabText(i)}
    def forget(self,child):
        child=_registry.get(str(child),child);self._q.removeTab(self._q.indexOf(qwidget(child)))
    hide=forget
    def index(self,tab):return self._q.currentIndex() if tab=='current' else self._q.indexOf(qwidget(_registry.get(str(tab),tab)))
class Panedwindow(Widget):
    qt_type=W.QSplitter
    def __init__(self,*args,**kw):super().__init__(*args,**kw);self._q.setOrientation(C.Qt.Orientation.Vertical if kw.get('orient')=='vertical' else C.Qt.Orientation.Horizontal)
    def add(self,child,**kw):self._q.addWidget(child._q);self._q.setStretchFactor(self._q.count()-1,int(kw.get('weight',1)));child._q.show()
class Text(Widget):
    qt_type=W.QTextEdit
    def insert(self,index,text):self._q.moveCursor(G.QTextCursor.MoveOperation.End);self._q.insertPlainText(str(text))
    def get(self,*args):return self._q.toPlainText()
    def delete(self,*args):self._q.clear()
    def configure(self,cnf=None,**kw):
        super().configure(cnf,**kw)
        if 'state' in kw:self._q.setEnabled(True);self._q.setReadOnly(kw['state']=='disabled')
class Listbox(Widget):
    qt_type=W.QListWidget
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw);self._q.setSelectionMode(W.QAbstractItemView.SelectionMode.ExtendedSelection if kw.get('selectmode') in ('extended','multiple') else W.QAbstractItemView.SelectionMode.SingleSelection);self._q.itemSelectionChanged.connect(lambda:self._emit('<<ListboxSelect>>'))
    def insert(self,index,*texts):
        for text in texts:self._q.addItem(str(text)) if index=='end' else self._q.insertItem(int(index),str(text))
    def delete(self,first,last=None):
        end=self._q.count()-1 if last=='end' else int(last if last is not None else first)
        for i in range(end,int(first)-1,-1):self._q.takeItem(i)
    def get(self,index):return self._q.item(int(index)).text()
    def curselection(self):return tuple(self._q.row(item) for item in self._q.selectedItems())
    def selection_set(self,first,last=None):
        end=self._q.count()-1 if last=='end' else int(last if last is not None else first)
        for i in range(int(first),end+1):
            if self._q.item(i):self._q.item(i).setSelected(True)
    def selection_clear(self,*args):self._q.clearSelection()
    def yview(self,*args):return _scroll(self._q.verticalScrollBar(),args)

def _scroll(bar,args):
    if args:
        if args[0]=='moveto':bar.setValue(round(float(args[1])*max(1,bar.maximum())))
        elif args[0]=='scroll':bar.setValue(bar.value()+int(args[1])*(bar.pageStep() if len(args)>2 and args[2]=='pages' else bar.singleStep()))
    total=bar.maximum()+bar.pageStep()
    return (bar.value()/total,(bar.value()+bar.pageStep())/total) if total>0 else (0.,1.)

class TableModel(C.QAbstractTableModel):
    def __init__(self,owner):super().__init__(owner._q);self.owner=owner;self.rows=[];self.records={};self.positions={}
    def rowCount(self,parent=C.QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=C.QModelIndex()):return len(self.owner._visible_columns())
    def data(self,index,role=C.Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row()>=len(self.rows):return None
        o=self.owner;rec=self.records[self.rows[index.row()]];columns=o._visible_columns()
        if index.column()>=len(columns):return None
        col=columns[index.column()];value=rec['text'] if col=='#0' else rec['values'][o._columns.index(col)] if o._columns.index(col)<len(rec['values']) else ''
        if role in (C.Qt.ItemDataRole.DisplayRole,C.Qt.ItemDataRole.ToolTipRole):return '' if value is None else str(value)
        if role==C.Qt.ItemDataRole.UserRole:return value
        if role==C.Qt.ItemDataRole.TextAlignmentRole:
            anchor=o._column_options.get(col,{}).get('anchor','w')
            return int(C.Qt.AlignmentFlag.AlignVCenter|(C.Qt.AlignmentFlag.AlignRight if anchor=='e' else C.Qt.AlignmentFlag.AlignHCenter if anchor=='center' else C.Qt.AlignmentFlag.AlignLeft))
        tags=rec['tags'];options={}
        for tag in tags:options.update(o._tags.get(tag,{}))
        if role==C.Qt.ItemDataRole.BackgroundRole and options.get('background'):return G.QColor(o._color(options['background']))
        if role==C.Qt.ItemDataRole.ForegroundRole and options.get('foreground'):return G.QColor(o._color(options['foreground']))
        if role==C.Qt.ItemDataRole.FontRole:
            from numeric_tree import numeric_cell
            return o._font(options.get('font'),numeric_cell(o._headings.get(col,{}).get('text',col),value)).q
        return None
    def headerData(self,section,orientation,role=C.Qt.ItemDataRole.DisplayRole):
        if orientation==C.Qt.Orientation.Horizontal and role==C.Qt.ItemDataRole.DisplayRole:
            cols=self.owner._visible_columns();return self.owner._headings.get(cols[section],{}).get('text',cols[section]) if section<len(cols) else ''
        return section+1 if role==C.Qt.ItemDataRole.DisplayRole else None
    def reset(self):
        self.beginResetModel();self.positions={iid:i for i,iid in enumerate(self.rows)};self.endResetModel()

class TableProxy(C.QSortFilterProxyModel):
    def lessThan(self,left,right):
        a=left.data(C.Qt.ItemDataRole.UserRole);b=right.data(C.Qt.ItemDataRole.UserRole)
        def numeric(v):
            if isinstance(v,(int,float)):return v
            return float(str(v).replace(',','').replace('원','').replace('%',''))
        try:return numeric(a)<numeric(b)
        except (ValueError,TypeError):return str(a or '').casefold()<str(b or '').casefold()

class Treeview(Widget):
    qt_type=W.QTableView
    def __init__(self,*args,**kw):
        self._columns=[];self._column_options={};self._headings={};self._tags={};self._hidden={};self._cell_grid=False;self._fonts={};self._font_by_name={};self._number_job=None;self._layout_warm_job=None;self._wrap_cells=False
        super().__init__(*args,**kw);self.model=TableModel(self);self.proxy=TableProxy(self._q);self.proxy.setSourceModel(self.model);self.proxy.setDynamicSortFilter(False);self._q.setModel(self.proxy);self._q.setSortingEnabled(True);self.proxy.sort(-1)
        self._q.setHorizontalScrollMode(W.QAbstractItemView.ScrollMode.ScrollPerPixel);self._q.setVerticalScrollMode(W.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._q.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows);self._q.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection if kw.get('selectmode')=='browse' else W.QAbstractItemView.SelectionMode.ExtendedSelection);self._q.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers);self._q.setAlternatingRowColors(True);self._q.setWordWrap(False);self._q.verticalHeader().setVisible(False);self._q.verticalHeader().setDefaultSectionSize(32);self._q.horizontalHeader().setStretchLastSection(False);self._q.setShowGrid(False)
        self._q.selectionModel().selectionChanged.connect(lambda *_:self._emit('<<TreeviewSelect>>'))
        self._q.horizontalHeader().sectionClicked.connect(self._header_clicked)
        self._q.viewport().installEventFilter(self._filter);self._q.viewport().setMouseTracking(True)
        for axis in ('x','y'):
            bar=self._q.horizontalScrollBar() if axis=='x' else self._q.verticalScrollBar();bar.valueChanged.connect(lambda v,a=axis:self._scroll_changed(a));bar.rangeChanged.connect(lambda lo,hi,a=axis:self._scroll_changed(a))
        self._sync_columns()
        from table_preferences import ColumnWidths
        self._width_preferences=ColumnWidths(self)
    def _container(self):return self._q.viewport()
    def _color(self,value):
        appearance=getattr(self._root(),'_appearance',None)
        if appearance:
            from appearance import color
            return color(value,appearance.theme)
        return value
    def _visible_columns(self):
        cols=self._options.get('displaycolumns',('#all',))
        if cols=='#all' or cols==('#all',) or cols==['#all'] or not cols:cols=self._columns
        else:cols=[self._columns[int(c)] if isinstance(c,int) else c for c in cols]
        return (['#0'] if 'tree' in str(self._options.get('show','headings')) else [])+list(cols)
    def _sync_columns(self):
        if not hasattr(self,'model'):return
        self.model.reset()
        for i,c in enumerate(self._visible_columns()):self._q.setColumnWidth(i,int(self._column_options.get(c,{}).get('width',140)))
    def configure(self,cnf=None,**kw):
        super().configure(cnf,**kw)
        if 'columns' in kw:self._columns=[str(c) for c in kw['columns']]
        if any(k in kw for k in ('columns','displaycolumns','show')):self._sync_columns()
        if 'style' in kw and hasattr(self,'model'):
            bar=self._q.verticalScrollBar();bottom=bar.maximum()>0 and bar.value()>=bar.maximum()-1
            height=int(Style(self).lookup(kw['style'],'rowheight') or 32)
            changed=height!=self._q.verticalHeader().defaultSectionSize()
            self._q.verticalHeader().setDefaultSectionSize(height)
            self._q.setWordWrap(self._wrap_cells)
            self._q.setTextElideMode(C.Qt.TextElideMode.ElideNone if self._wrap_cells else C.Qt.TextElideMode.ElideRight)
            if changed:
                self._q.doItemsLayout()
                if bottom:self._q.scrollToBottom()
        if 'selectmode' in kw:self._q.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection if kw['selectmode']=='browse' else W.QAbstractItemView.SelectionMode.ExtendedSelection)
    config=configure
    def cget(self,key):
        if key=='columns':return tuple(self._columns)
        if key=='displaycolumns':return self._options.get(key,('#all',))
        if key=='show':return self._options.get(key,'headings')
        return super().cget(key)
    def _header_clicked(self,section):
        col=self._visible_columns()[section];callback=self._headings.get(col,{}).get('command')
        if callback:_invoke(callback)
    def heading(self,column,option=None,**kw):
        c=self._resolve_column(column);data=self._headings.setdefault(c,{'text':c,'anchor':'center'});data.update(kw)
        if hasattr(self,'model') and kw:self.model.headerDataChanged.emit(C.Qt.Orientation.Horizontal,0,max(0,len(self._visible_columns())-1))
        return data.get(option,'') if option else data.copy()
    def _resolve_column(self,c):
        if isinstance(c,int):return self._columns[c]
        if str(c).startswith('#') and c!='#0':
            idx=int(str(c)[1:])-1;return self._visible_columns()[idx] if 0<=idx<len(self._visible_columns()) else str(c)
        return str(c)
    def column(self,column,option=None,**kw):
        c=self._resolve_column(column)
        if 'width' in kw and hasattr(self,'_width_preferences'):kw['width']=self._width_preferences.width(c,kw['width'])
        data=self._column_options.setdefault(c,{'id':c,'width':140,'minwidth':30,'stretch':True,'anchor':'w'});data.update(kw)
        cols=self._visible_columns()
        if kw and c in cols and hasattr(self,'model'):
            i=cols.index(c)
            if 'width' in kw:self._q.setColumnWidth(i,int(kw['width']))
        return data.get(option,'') if option else data.copy()
    def insert(self,parent,index,iid=None,**kw):
        iid=str(iid) if iid is not None else 'I'+str(next(_ids))
        if iid in self.model.records:raise ValueError('Duplicate item ID: '+iid)
        pos=len(self.model.rows) if index=='end' else int(index);self.model.beginInsertRows(C.QModelIndex(),pos,pos);self.model.rows.insert(pos,iid);self.model.records[iid]={'values':list(kw.get('values',())),'tags':tuple(kw.get('tags',())),'text':kw.get('text',''),'open':kw.get('open',False),'parent':parent};self.model.positions[iid]=pos;self.model.endInsertRows();return iid
    def get_children(self,item=None):return tuple(self.model.rows)
    def delete(self,*items):
        ids=list(_flatten(items))
        if not ids:return
        if len(ids)==len(self.model.rows) and set(ids)==set(self.model.rows):self.model.rows.clear();self.model.records.clear();self.model.reset();return
        for iid in ids:
            if iid in self.model.rows:self.model.rows.remove(iid)
            self.model.records.pop(iid,None)
        self.model.reset()
    def item(self,iid,option=None,**kw):
        rec=self.model.records[str(iid)];rec.update(kw)
        if kw:
            row=self.model.rows.index(str(iid));self.model.dataChanged.emit(self.model.index(row,0),self.model.index(row,max(0,self.model.columnCount()-1)))
        return rec.get(option) if option else rec.copy()
    def set(self,iid,column=None,value=None):
        rec=self.model.records[str(iid)]
        if column is None:return dict(zip(self._columns,rec['values']))
        c=self._resolve_column(column);i=self._columns.index(c)
        if value is None:return rec['values'][i] if i<len(rec['values']) else ''
        while len(rec['values'])<=i:rec['values'].append('')
        rec['values'][i]=value;self.item(iid,values=rec['values'])
    def selection(self):return tuple(self.model.rows[self.proxy.mapToSource(index).row()] for index in self._q.selectionModel().selectedRows())
    def selection_set(self,*items):
        self._q.clearSelection()
        for iid in _flatten(items):
            if str(iid) not in self.model.rows:continue
            index=self.proxy.mapFromSource(self.model.index(self.model.rows.index(str(iid)),0));self._q.selectionModel().select(index,C.QItemSelectionModel.SelectionFlag.Select|C.QItemSelectionModel.SelectionFlag.Rows)
    def selection_remove(self,*items):
        selected=set(self.selection())-set(_flatten(items));self.selection_set(tuple(selected))
    def selection_add(self,*items):self.selection_set((*self.selection(),*_flatten(items)))
    def focus(self,iid=None):
        if iid is None:
            index=self.proxy.mapToSource(self._q.currentIndex());return self.model.rows[index.row()] if index.isValid() else ''
        if iid in self.model.rows:self._q.setCurrentIndex(self.proxy.mapFromSource(self.model.index(self.model.rows.index(iid),0)))
    def exists(self,iid):return str(iid) in self.model.records
    def index(self,iid):return self.model.rows.index(str(iid))
    def move(self,iid,parent,index):
        self.model.rows.remove(iid);self.model.rows.insert(len(self.model.rows) if index=='end' else int(index),iid);self.model.reset()
    def detach(self,*items):
        for iid in items:
            if iid in self.model.rows:self.model.rows.remove(iid);self._hidden[iid]=True
        self.model.reset()
    def set_children(self,item,*children):self.model.rows=list(children);self.model.reset()
    def tag_configure(self,tagname,option=None,**kw):
        options=self._tags.setdefault(tagname,{});options.update(kw)
        if hasattr(self,'model') and kw:self._q.viewport().update()
        return options.get(option,'') if option else options.copy()
    tag_config=tag_configure
    def identify_row(self,y):
        index=self._q.indexAt(C.QPoint(5,int(y)))
        return self.model.rows[self.proxy.mapToSource(index).row()] if index.isValid() else ''
    def identify_column(self,x):
        col=self._q.columnAt(int(x));return '#'+str(col if '#0' in self._visible_columns() else col+1) if col>=0 else ''
    def identify_region(self,x,y):return 'cell' if self.identify_row(y) else 'heading' if y<self._q.horizontalHeader().height() else 'nothing'
    def bbox(self,iid,column=None):
        if iid not in self.model.rows:return ()
        cols=self._visible_columns();c=0 if column is None else cols.index(self._resolve_column(column));index=self.proxy.mapFromSource(self.model.index(self.model.rows.index(iid),c));rect=self._q.visualRect(index)
        if not rect.intersects(self._q.viewport().rect()):return ()
        return rect.x(),rect.y(),rect.width(),rect.height()
    def see(self,iid):
        if iid in self.model.rows:self._q.scrollTo(self.proxy.mapFromSource(self.model.index(self.model.rows.index(iid),0)))
    def xview(self,*args):return _scroll(self._q.horizontalScrollBar(),args)
    def yview(self,*args):return _scroll(self._q.verticalScrollBar(),args)
    def xview_moveto(self,v):return self.xview('moveto',v)
    def yview_moveto(self,v):return self.yview('moveto',v)
    def yview_scroll(self,n,what):return self.yview('scroll',n,what)
    def xview_scroll(self,n,what):return self.xview('scroll',n,what)
    def _scroll_changed(self,axis):
        if not self.winfo_exists():return
        callback=self._options.get(axis+'scrollcommand')
        if callback:_invoke(callback,*(self.xview() if axis=='x' else self.yview()))
    def refresh_numbers(self,*args):self._q.setShowGrid(bool(self._cell_grid));self._q.viewport().update()
    refresh_grid=refresh_numbers
    def _font(self,spec=None,numeric=False):
        appearance=getattr(self._root(),'_appearance',None)
        raw=spec or self._q.font();signature=raw.toString() if isinstance(raw,G.QFont) else str(raw)
        key=(signature,numeric,appearance.family if appearance else '',appearance.numeric_family if appearance else '')
        cache=getattr(self,'_resolved_fonts',None)
        if cache is None:cache={};self._resolved_fonts=cache
        if key in cache:return cache[key]
        f=Font(font=raw)
        if appearance:f.q.setFamily((appearance.numeric_family or appearance.family) if numeric else appearance.family)
        cache[key]=f;self._fonts[str(f)]=f;return f
    def _character_width(self,name,char):return _fonts[name].measure(char)
    def wrap_text(self,text,font,width):
        result=[]
        for paragraph in str(text).split('\n'):
            line=''
            for char in paragraph:
                if line and font.measure(line+char)>width:result.append(line);line=''
                line+=char
            result.append(line)
        return '\n'.join(result)

class PhotoImage:
    def __init__(self,image=None,master=None,file=None,**kw):
        application()
        if file:self.pixmap=G.QPixmap(str(file))
        elif image is not None:
            from PIL.ImageQt import ImageQt
            self.pixmap=G.QPixmap.fromImage(ImageQt(image))
        else:self.pixmap=G.QPixmap()
    def width(self):return self.pixmap.width()
    def height(self):return self.pixmap.height()

class Canvas(Widget):
    qt_type=W.QGraphicsView
    def __init__(self,*args,**kw):
        self._items={};self._hovered=set();self._tag_bindings={};self._z=0
        super().__init__(*args,**kw);self.scene=W.QGraphicsScene(self._q);self._q.setScene(self.scene);self._q.setRenderHints(G.QPainter.RenderHint.Antialiasing|G.QPainter.RenderHint.TextAntialiasing|G.QPainter.RenderHint.SmoothPixmapTransform);self._q.setAlignment(C.Qt.AlignmentFlag.AlignLeft|C.Qt.AlignmentFlag.AlignTop);self._q.setFrameShape(W.QFrame.Shape.NoFrame);self._q.viewport().installEventFilter(self._filter);self._q.viewport().setMouseTracking(True)
        self._q.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self._q.setVerticalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._q.verticalScrollBar().valueChanged.connect(lambda _:self._scroll_changed())
        self.configure(**kw)
    def configure(self,cnf=None,**kw):
        super().configure(cnf,**kw)
        if hasattr(self,'scene'):
            bg=kw.get('bg',kw.get('background'))
            if bg:self._q.setBackgroundBrush(G.QBrush(G.QColor(self._color(bg))))
            if 'scrollregion' in kw and kw['scrollregion']:
                x,y,x2,y2=kw['scrollregion'];self.scene.setSceneRect(float(x),float(y),max(0,float(x2)-float(x)),max(0,float(y2)-float(y)))
    config=configure
    def _color(self,value):
        appearance=getattr(self._root(),'_appearance',None)
        if appearance:
            from appearance import color
            return color(value,appearance.theme)
        return value
    def _create(self,kind,args,options):
        coords=list(_flatten(args));options=dict(options);item_id=next(_ids)
        if kind=='text':item=W.QGraphicsTextItem();item.setPlainText(str(options.get('text','')))
        elif kind=='image':item=W.QGraphicsPixmapItem(options['image'].pixmap)
        elif kind=='window':
            child=options['window'];child._q.setParent(None);item=self.scene.addWidget(child._q);child._q.show()
        elif kind=='rectangle':item=W.QGraphicsRectItem(C.QRectF(float(coords[0]),float(coords[1]),float(coords[2])-float(coords[0]),float(coords[3])-float(coords[1])))
        elif kind=='oval':item=W.QGraphicsEllipseItem(C.QRectF(float(coords[0]),float(coords[1]),float(coords[2])-float(coords[0]),float(coords[3])-float(coords[1])))
        elif kind in ('line','polygon'):
            path=G.QPainterPath(C.QPointF(float(coords[0]),float(coords[1])))
            for x,y in zip(coords[2::2],coords[3::2]):path.lineTo(float(x),float(y))
            if kind=='polygon':path.closeSubpath()
            item=W.QGraphicsPathItem(path)
        else:raise ValueError('Unsupported canvas primitive: '+kind)
        if item.scene() is None:self.scene.addItem(item)
        tags=options.get('tags',());tags=(tags,) if isinstance(tags,str) else tuple(tags)
        self._items[item_id]={'item':item,'kind':kind,'coords':coords,'options':options,'tags':tags};self._z+=1;item.setZValue(self._z);self._apply_item(item_id);return item_id
    def _apply_item(self,identity):
        rec=self._items[identity];item=rec['item'];o=rec['options'];coords=rec['coords'];kind=rec['kind']
        if kind=='text':
            item.setPlainText(str(o.get('text','')));f=Font(font=o.get('font')).q;app=getattr(self._root(),'_appearance',None)
            if app:
                from appearance import ChartFont,NumericFont
                f.setFamily((app.chart_family or app.family) if isinstance(o.get('font'),ChartFont) else (app.numeric_family or app.family) if isinstance(o.get('font'),NumericFont) else app.family)
            item.setFont(f);item.setDefaultTextColor(G.QColor(self._color(o.get('fill','#E2E8F0'))));item.setTextWidth(float(o.get('width',-1) or -1));item.document().setDocumentMargin(0)
        elif kind not in ('image','window'):
            fill=o.get('fill','');outline=o.get('fill','') if kind=='line' else o.get('outline','')
            item.setBrush(G.QBrush(G.QColor(self._color(fill))) if fill and kind!='line' else C.Qt.BrushStyle.NoBrush)
            pen=G.QPen(G.QColor(self._color(outline))) if outline else G.QPen(C.Qt.PenStyle.NoPen);pen.setWidthF(float(o.get('width',1)));item.setPen(pen)
        if kind in ('text','image','window'):
            if kind=='window':
                if 'width' in o:item.resize(float(o['width']),item.size().height())
                if 'height' in o:item.resize(item.size().width(),float(o['height']))
            rect=item.boundingRect();anchor=o.get('anchor','center');x,y=map(float,coords[:2]);x-=0 if 'w' in anchor else rect.width() if 'e' in anchor else rect.width()/2;y-=0 if 'n' in anchor else rect.height() if 's' in anchor else rect.height()/2;item.setPos(x,y)
        item.setVisible(o.get('state')!='hidden')
    def create_text(self,*args,**kw):return self._create('text',args,kw)
    def create_rectangle(self,*args,**kw):return self._create('rectangle',args,kw)
    def create_oval(self,*args,**kw):return self._create('oval',args,kw)
    def create_polygon(self,*args,**kw):return self._create('polygon',args,kw)
    def create_line(self,*args,**kw):return self._create('line',args,kw)
    def create_image(self,*args,**kw):return self._create('image',args,kw)
    def create_window(self,*args,**kw):return self._create('window',args,kw)
    def _matching(self,tag):
        if tag=='all':return list(self._items)
        if isinstance(tag,int) or str(tag).isdigit():return [int(tag)] if int(tag) in self._items else []
        return [i for i,r in self._items.items() if tag in r['tags']]
    def delete(self,*tags):
        for tag in tags:
            for i in self._matching(tag):
                rec=self._items.pop(i);item=rec['item']
                if rec['kind']=='window':item.setWidget(None)
                self.scene.removeItem(item)
                app=getattr(self._root(),'_appearance',None)
                if app and self in app.items:app.items[self].pop(i,None)
    def find_all(self):return tuple(self._items)
    def find_withtag(self,tag):return tuple(self._matching(tag))
    def type(self,i):return self._items.get(i,{}).get('kind','')
    def itemconfigure(self,tag,cnf=None,**kw):
        options=_cnfmerge((cnf,kw))
        for i in self._matching(tag):
            self._items[i]['options'].update(options);self._apply_item(i)
    itemconfig=itemconfigure
    def itemcget(self,i,option):
        rec=self._items[i]
        if option=='font' and rec['kind']=='text':return Font(font=rec['item'].font())
        value=rec['options'].get(option,'')
        return self._color(value) if option in ('fill','outline') else value
    def coords(self,i,*coords):
        if not coords:return list(self._items[i]['coords'])
        self._items[i]['coords']=list(_flatten(coords));self._apply_item(i)
    def bbox(self,tag):
        items=[self._items[i]['item'].sceneBoundingRect() for i in self._matching(tag)]
        if not items:return ()
        rect=items[0]
        for other in items[1:]:rect=rect.united(other)
        return rect.left(),rect.top(),rect.right(),rect.bottom()
    def tag_raise(self,tag,*args):
        for i in self._matching(tag):self._z+=1;self._items[i]['item'].setZValue(self._z)
    def tag_lower(self,tag,*args):
        for i in self._matching(tag):self._items[i]['item'].setZValue(-1)
    def tag_bind(self,tag,sequence,callback,add=None):self._tag_bindings.setdefault((tag,sequence),[]).append(callback)
    def _hover(self,extra):
        point=self._q.mapToScene(C.QPoint(extra.get('x',0),extra.get('y',0)));hit={i for i,r in self._items.items() if r['item'].isVisible() and r['item'].sceneBoundingRect().contains(point) and r['options'].get('state')!='disabled'}
        event=SimpleNamespace(**dict(dict(widget=self,x=0,y=0),**extra))
        for (tag,sequence),callbacks in self._tag_bindings.items():
            matches=set(self._matching(tag));before=bool(matches&self._hovered);now=bool(matches&hit)
            if (sequence=='<Enter>' and now and not before) or (sequence=='<Leave>' and before and not now) or (sequence=='<Motion>' and now):
                for callback in callbacks:_invoke(callback,event)
        self._hovered=hit
    def canvasx(self,x):return self._q.mapToScene(C.QPoint(int(x),0)).x()
    def canvasy(self,y):return self._q.mapToScene(C.QPoint(0,int(y))).y()
    def xview(self,*args):return _scroll(self._q.horizontalScrollBar(),args)
    def yview(self,*args):return _scroll(self._q.verticalScrollBar(),args)
    def xview_moveto(self,v):return self.xview('moveto',v)
    def yview_moveto(self,v):return self.yview('moveto',v)
    def yview_scroll(self,n,what):return self.yview('scroll',n,what)
    def _scroll_changed(self):
        if not self.winfo_exists():return
        callback=self._options.get('yscrollcommand')
        if callback:_invoke(callback,*self.yview())

class Style:
    _styles={};_maps={}
    def __init__(self,master=None):self.master=master or _default_root
    def theme_use(self,*args):return 'Fusion'
    def configure(self,name,option=None,**kw):
        data=self._styles.setdefault(name,{});data.update(kw)
        return data.get(option,'') if option else data.copy()
    config=configure
    def map(self,name,**kw):self._maps.setdefault(name,{}).update(kw)
    def lookup(self,name,option,state=(),default=None):
        states=self._maps.get(name,{}).get(option,[])
        for values in states:
            if state and state[0] in values[:-1]:return values[-1]
        defaults={'font':('맑은 고딕',10),'background':'#172231','foreground':'#E2E8F0','rowheight':32}
        return self._styles.get(name,{}).get(option,self._styles.get('.',{}).get(option,defaults.get(option,default or '')))

class Dialogs:
    @staticmethod
    def _filter(options):return ';;'.join(f'{name} ({patterns})' for name,patterns in options.get('filetypes',[('모든 파일','*')]))
    @staticmethod
    def askopenfilename(**kw):application();return W.QFileDialog.getOpenFileName(qwidget(kw.get('parent')),kw.get('title','파일 선택'),str(kw.get('initialdir','')),Dialogs._filter(kw))[0]
    @staticmethod
    def askopenfilenames(**kw):application();return tuple(W.QFileDialog.getOpenFileNames(qwidget(kw.get('parent')),kw.get('title','파일 선택'),str(kw.get('initialdir','')),Dialogs._filter(kw))[0])
    @staticmethod
    def asksaveasfilename(**kw):application();return W.QFileDialog.getSaveFileName(qwidget(kw.get('parent')),kw.get('title','저장'),str(kw.get('initialdir',''))+'/'+kw.get('initialfile',''),Dialogs._filter(kw))[0]
    @staticmethod
    def askdirectory(**kw):application();return W.QFileDialog.getExistingDirectory(qwidget(kw.get('parent')),kw.get('title','폴더 선택'),str(kw.get('initialdir','')))
filedialog=Dialogs
class Messages:
    @staticmethod
    def showinfo(title,message,**kw):application();return W.QMessageBox.information(qwidget(kw.get('parent')),str(title),str(message))
    @staticmethod
    def showerror(title,message,**kw):application();return W.QMessageBox.critical(qwidget(kw.get('parent')),str(title),str(message))
    @staticmethod
    def showwarning(title,message,**kw):application();return W.QMessageBox.warning(qwidget(kw.get('parent')),str(title),str(message))
    @staticmethod
    def askyesno(title,message,**kw):application();return W.QMessageBox.question(qwidget(kw.get('parent')),str(title),str(message),W.QMessageBox.StandardButton.Yes|W.QMessageBox.StandardButton.No,W.QMessageBox.StandardButton.No)==W.QMessageBox.StandardButton.Yes
    askokcancel=askyesno
messagebox=Messages
class Inputs:
    @staticmethod
    def askstring(title,prompt,**kw):application();text,ok=W.QInputDialog.getText(qwidget(kw.get('parent')),title,prompt,text=str(kw.get('initialvalue','')));return text if ok else None
    @staticmethod
    def askinteger(title,prompt,**kw):application();v,ok=W.QInputDialog.getInt(qwidget(kw.get('parent')),title,prompt,int(kw.get('initialvalue',0)),int(kw.get('minvalue',-2147483647)),int(kw.get('maxvalue',2147483647)));return v if ok else None
simpledialog=Inputs
ImageTk=SimpleNamespace(PhotoImage=PhotoImage)
ttk=SimpleNamespace(**{name:globals()[name] for name in ('Frame','LabelFrame','Label','Button','Entry','Combobox','Spinbox','Checkbutton','Radiobutton','Progressbar','Separator','Scrollbar','Scale','Notebook','Panedwindow','Treeview','Style')})

class Tcl:
    """Parse drag/drop lists without loading Tcl (also accepts native Qt URL lists)."""
    def splitlist(self,value):
        if isinstance(value,(tuple,list)):return tuple(value)
        result=[];buf=[];depth=0;quoted=False;started=False
        for char in str(value):
            if char=='{' and not quoted:
                if depth:buf.append(char)
                depth+=1;started=True
            elif char=='}' and depth and not quoted:
                depth-=1
                if depth:buf.append(char)
            elif char=='"' and not depth:quoted=not quoted;started=True
            elif char.isspace() and not depth and not quoted:
                if started:result.append(''.join(buf));buf=[];started=False
            else:buf.append(char);started=True
        if depth or quoted:raise ValueError('Invalid file list')
        if started:result.append(''.join(buf))
        return tuple(result)

Misc=Widget

class NavigationTree(Widget):
    """Hierarchical Qt navigation with recursive search and stable command IDs."""
    qt_type=W.QTreeView
    def __init__(self,*args,**kw):
        super().__init__(*args,**kw);self.model=G.QStandardItemModel(self._q);self.proxy=C.QSortFilterProxyModel(self._q);self.proxy.setSourceModel(self.model);self.proxy.setRecursiveFilteringEnabled(True);self.proxy.setFilterCaseSensitivity(C.Qt.CaseSensitivity.CaseInsensitive);self._q.setModel(self.proxy);self._q.setHeaderHidden(True);self._q.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers);self._q.setUniformRowHeights(True);self._nodes={};self._q.selectionModel().selectionChanged.connect(lambda *_:self._emit('<<TreeviewSelect>>'));self._q.setMinimumWidth(190)
    def insert(self,parent,index,iid=None,**kw):
        iid=str(iid or next(_ids));node=G.QStandardItem(str(kw.get('text','')));node.setData(iid,C.Qt.ItemDataRole.UserRole);self._nodes[iid]=node
        owner=self._nodes[parent] if parent else self.model.invisibleRootItem();owner.appendRow(node)
        if kw.get('open'):self._q.expand(self.proxy.mapFromSource(node.index()))
        return iid
    def selection(self):return tuple(index.data(C.Qt.ItemDataRole.UserRole) for index in self._q.selectionModel().selectedRows())
    def selection_set(self,iid):self._q.setCurrentIndex(self.proxy.mapFromSource(self._nodes[str(iid)].index()))
    def column(self,column,option=None,**kw):
        if 'width' in kw:self._q.setColumnWidth(0,int(kw['width']))
        return self._q.columnWidth(0)
    def yview(self,*args):return _scroll(self._q.verticalScrollBar(),args)
    def filter(self,value):self.proxy.setFilterFixedString(value);self._q.expandAll()
    def get_children(self,parent=''):
        item=self._nodes[parent] if parent else self.model.invisibleRootItem();return tuple(item.child(i).data(C.Qt.ItemDataRole.UserRole) for i in range(item.rowCount()))

ttk.NavigationTree=NavigationTree
