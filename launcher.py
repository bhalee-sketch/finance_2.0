"""작은 세로 메뉴와 화면 우측 상단의 반투명 상시 표시 메뉴."""
import sys
import re
import json
from pathlib import Path
import qt_ui as tk
from qt_ui import messagebox
from qt_ui import ttk
from app_version import application_title


def work_area(root):
    """현재 창이 있는 모니터의 작업 영역(음수 좌표 포함)."""
    if hasattr(root,'_q') and isinstance(root._q,tk.W.QWidget):
        rect=root._q.screen().availableGeometry()
        return rect.left(),rect.top(),rect.right()+1,rect.bottom()+1
    if sys.platform=='win32':
        try:
            import ctypes
            from ctypes import wintypes
            class INFO(ctypes.Structure):
                _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
            api=ctypes.windll.user32
            api.MonitorFromPoint.argtypes=[wintypes.POINT,wintypes.DWORD];api.MonitorFromPoint.restype=wintypes.HANDLE
            api.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(INFO)]
            api.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];api.GetAncestor.restype=wintypes.HWND
            api.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
            rect=wintypes.RECT()
            if api.GetWindowRect(api.GetAncestor(root.winfo_id(),2),ctypes.byref(rect)):
                point=wintypes.POINT((rect.left+rect.right)//2,(rect.top+rect.bottom)//2)
            else:point=wintypes.POINT(root.winfo_x()+root.winfo_width()//2,root.winfo_y()+root.winfo_height()//2)
            monitor=api.MonitorFromPoint(point,2);info=INFO();info.size=ctypes.sizeof(info)
            if api.GetMonitorInfoW(monitor,ctypes.byref(info)):
                r=info.work;return r.left,r.top,r.right,r.bottom
        except (AttributeError,OSError):pass
    return 0,0,root.winfo_screenwidth(),root.winfo_screenheight()


def virtual_area(root):
    if hasattr(root,'_q') and isinstance(root._q,tk.W.QWidget):
        rect=tk.C.QRect()
        for screen in tk.application().screens():rect=rect.united(screen.geometry())
        return rect.left(),rect.top(),rect.right()+1,rect.bottom()+1
    if sys.platform=='win32':
        import ctypes
        api=ctypes.windll.user32
        x,y,w,h=[api.GetSystemMetrics(i) for i in (76,77,78,79)]
        if w>0 and h>0:return x,y,x+w,y+h
    return work_area(root)


def position(root,w,h,x,y):
    if hasattr(root,'_q') and isinstance(root._q,tk.W.QWidget):
        root._q.setGeometry(int(x),int(y),int(w),int(h));return
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        api=ctypes.windll.user32
        api.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT];api.GetAncestor.restype=wintypes.HWND
        api.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        root.geometry(f'{w}x{h}');root.update_idletasks()
        hwnd=api.GetAncestor(root.winfo_id(),2)
        api.SetWindowPos(hwnd,None,int(x),int(y),int(w),int(h),0x14)
    else:root.geometry(f'{w}x{h}{x:+d}{y:+d}')


DEFAULTS={'opacity':85, 'size':100, 'text_scale':110, 'text_sizes':{}, 'hover':True, 'topmost':True, 'theme':'light', 'font':'Paperlogy', 'chart_font':'', 'numeric_font':'', 'lock_position':False, 'view_mode':'workspace'}


def load_preferences(path):
    try:
        data=json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data,dict):return dict(DEFAULTS)
        result=dict(DEFAULTS)
        for key,low,high in (('opacity',30,100),('size',75,130),('text_scale',80,150)):
            value=data.get(key)
            if isinstance(value,(int,float)) and low<=value<=high:result[key]=int(value)
        sizes=data.get('text_sizes',{})
        if isinstance(sizes,dict):result['text_sizes']={key:float(value) for key,value in sizes.items() if key in ('system','description','data') and isinstance(value,(int,float)) and 8<=value<=28}
        for key in ('hover','topmost','lock_position'):
            if isinstance(data.get(key),bool):result[key]=data[key]
        if data.get('theme') in ('dark','light'):result['theme']=data['theme']
        elif 'theme' in data:result['theme']='dark'
        if isinstance(data.get('font'),str) and data['font'].strip() and len(data['font'])<=120:result['font']=data['font'].strip()
        if isinstance(data.get('chart_font'),str) and len(data['chart_font'])<=120:result['chart_font']=data['chart_font'].strip()
        if data.get('view_mode') in ('compact','workspace'):result['view_mode']=data['view_mode']
        elif 'view_mode' in data:result['view_mode']='compact'
        if isinstance(data.get('numeric_font'),str) and len(data['numeric_font'])<=120:result['numeric_font']=data['numeric_font'].strip()
        if isinstance(data.get('registered_fonts'),list):result['registered_fonts']=list(dict.fromkeys(v.strip() for v in data['registered_fonts'] if isinstance(v,str) and v.strip() and len(v)<=120))
        for key in ('favorite_workflows','recent_workflows'):
            if isinstance(data.get(key),list):result[key]=list(dict.fromkeys(v for v in data[key] if isinstance(v,str) and len(v)<=120))[:50]
        heights=data.get('page_heights',{})
        if isinstance(heights,dict):
            valid_heights={k:v for k,v in heights.items() if isinstance(k,str) and (k=='home' or k.isdigit()) and type(v) is int and 220<=v<=3000}
            if valid_heights:result['page_heights']=valid_heights
        geometry=data.get('geometry')
        if isinstance(geometry,list) and len(geometry)==4 and all(type(v) is int for v in geometry):
            if 270<=geometry[0]<=4000 and 220<=geometry[1]<=3000:result['geometry']=geometry
        return result
    except (OSError,ValueError,TypeError):return dict(DEFAULTS)


def save_preferences(path,preferences):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(preferences,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


class Launcher:
    def __init__(self,root,groups,settings_path,*,work_settings=None):
        self.work_settings=Path(work_settings) if work_settings is not None else Path(settings_path).parent
        self.settings_path=Path(settings_path);self.preferences=load_preferences(settings_path)
        from appearance import set_appearance
        set_appearance(root,self.preferences['theme'],self.preferences['font'],self.preferences.get('chart_font',''),self.preferences.get('numeric_font',''),self.preferences.get('text_scale',110),self.preferences.get('text_sizes'))
        self.settings_window=None
        self.root=root;self.groups=groups;self.cards=[card for _,cards in groups for card in cards];self.compact=self.preferences.get('view_mode')!='workspace';self.workspace=None;self.normal_geometry=None;self.active_group=None
        root.overrideredirect(True);root.attributes('-topmost',self.preferences['topmost']);root.attributes('-alpha',self.preferences['opacity']/100)
        self.frame=None;self.fade_job=None;self.drag_start=None;self.floating=False;self.expanded_size=None

        root.bind('<Enter>',self.enter,add='+');root.bind('<Leave>',self.leave,add='+')
        root.bind('<Escape>',lambda e:self.navigate(None) if self.active_group is not None else None,add='+')
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.render();self.place(center=True)
        root.resizable(not self.compact,not self.compact)
        from windows_taskbar import enable_taskbar
        enable_taskbar(root)

    def close(self):
        if self.root.grab_current() is None:self.root.destroy()

    def navigate(self,index):
        if self.root.grab_current() is not None:return
        self.active_group=index;self.render();self.place()

    def page_key(self):return 'home' if self.active_group is None else str(self.active_group)

    def render(self):
        self.compact=self.preferences.get('view_mode','compact')!='workspace'
        self.root.overrideredirect(self.compact or self.floating)
        self.root.resizable(not self.compact and not self.floating,not self.compact and not self.floating)
        self.root.attributes('-alpha',self.preferences['opacity']/100 if self.compact or self.floating else 1.0)
        if not self.compact and not self.floating:
            if self.frame is not None:self.frame.destroy();self.frame=None
            if self.workspace is None:
                from workspace_ui import Workspace
                self.workspace=Workspace(self)
            self.workspace.show()
            return
        if self.workspace is not None:self.workspace.hide()
        if self.frame is not None:self.frame.destroy()
        if self.floating:
            self.frame=tk.Canvas(self.root,width=128,height=34,bg='#101722',highlightthickness=0,cursor='fleur')
            self.frame.pack(fill='both',expand=True)
            self.frame.create_rectangle(2,2,126,32,fill='#203B53',outline='#65DCC7',width=2)
            self.frame.create_text(64,17,text='Work Space ▸',fill='#EAF9F7',font=('맑은 고딕',10,'bold'))
            self.frame.bind('<ButtonPress-1>',lambda e:self.start_drag(e,False));self.frame.bind('<B1-Motion>',self.drag)
            def release(event):
                moved=self.drag_start and (abs(event.x_root-self.drag_start[0])+abs(event.y_root-self.drag_start[1])>5)
                self.end_drag(event)
                if not moved:self.toggle_float()
            self.frame.bind('<ButtonRelease-1>',release)
            return
        factor=self.preferences['size']/100
        style=ttk.Style(self.root)
        style.configure('Launcher.TButton',anchor='w',padding=(14,max(4,round(9*factor))),font=('맑은 고딕',max(8,round(11*factor))))
        style.configure('Floating.TButton',anchor='w',padding=(10,max(3,round(6*factor))),font=('맑은 고딕',max(8,round(10*factor))))
        self.frame=ttk.Frame(self.root,padding=round((12 if self.compact else 20)*factor))
        self.frame.pack(fill='both',expand=True)
        header=ttk.Frame(self.frame);header.pack(fill='x',pady=(0,10))
        title=ttk.Label(header,text=application_title(),style='Accent.TLabel');title.pack(side='left')
        if self.compact:
            for widget in (title,header):
                widget.configure(cursor='fleur')
                widget.bind('<ButtonPress-1>',lambda e:self.start_drag(e,False))
                widget.bind('<B1-Motion>',self.drag)
                widget.bind('<ButtonRelease-1>',self.end_drag)
        from launcher_widgets import MenuButton,tooltip,settings_icon
        for symbol,label,command in (('×','종료',self.close),('▣','플로팅',self.toggle_float),('⚙','설정',self.customize)):
            button=ttk.Button(header,text=symbol,width=2,command=command,style='Compact.TButton',padding=(5,4),cursor='hand2')
            settings_icon(button,max(16,round(18*factor)),{'설정':'settings','플로팅':'floating','종료':'close'}[label])
            button.pack(side='right',padx=(3,0));tooltip(button,label)
        footer=ttk.Frame(self.frame);footer.pack(side='bottom',fill='x',pady=(3,0))
        from version_status import bind_status_label
        version=ttk.Label(footer,style='Muted.TLabel',wraplength=320)
        version.pack(side='left',fill='x')
        bind_status_label(self.root,version._q)
        if self.compact:
            grip=ttk.Label(footer,text='◢',cursor='size_nw_se' if sys.platform=='win32' else 'bottom_right_corner');grip.pack(side='right')
            grip.bind('<ButtonPress-1>',lambda e:self.start_drag(e,True))
            grip.bind('<B1-Motion>',self.drag);grip.bind('<ButtonRelease-1>',self.end_drag)
        area=ttk.Frame(self.frame);area.pack(fill='both',expand=True)
        canvas=tk.Canvas(area,highlightthickness=0,bg='#0D1420',width=300,
                         height=180)
        scroll=ttk.Scrollbar(area,command=canvas.yview)
        def scroll_state(first,last):
            scroll.set(first,last)
            if float(first)<=0 and float(last)>=1:scroll.pack_forget()
            else:scroll.pack(side='right',fill='y',before=canvas)
        canvas.configure(yscrollcommand=scroll_state);canvas.pack(fill='both',expand=True)
        menu=ttk.Frame(canvas);item=canvas.create_window(0,0,window=menu,anchor='nw')
        menu.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        icons=('▤','◈','▦','◇','⊞')
        for i,(name,cards) in enumerate(self.groups):
            selected=i==self.active_group
            button=MenuButton(menu,f'{icons[i%len(icons)]}  {name}',lambda index=i:self.navigate(None if self.active_group==index else index),selected=selected,factor=factor)
            button.pack(fill='x',pady=(0,4))
            button.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
            if selected:
                for label,command in cards:
                    caption=re.sub(r'^\d+\s+','',label.split('\n')[0])
                    child=MenuButton(menu,'›  '+caption,command,child=True,factor=factor)
                    child.pack(fill='x',pady=(0,1))
                    child.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))
        menu.update_idletasks();canvas.configure(width=max(300,menu.winfo_reqwidth()),height=menu.winfo_reqheight())
        canvas.bind('<MouseWheel>',lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,'units'))

    def start_drag(self,event,resize):
        if self.root.grab_current() is not None:return
        if not resize and self.preferences.get('lock_position',False):return
        self.drag_start=(event.x_root,event.y_root,self.root.winfo_x(),self.root.winfo_y(),
                         self.root.winfo_width(),self.root.winfo_height(),resize)

    def drag(self,event):
        if not self.compact or self.drag_start is None:return
        sx,sy,x,y,w,h,resize=self.drag_start;dx=event.x_root-sx;dy=event.y_root-sy
        left,top,right,bottom=virtual_area(self.root)
        if resize:w=max(360,min(right-x,w+dx));h=max(220,min(bottom-y,h+dy))
        else:x=max(left,min(right-w,x+dx));y=max(top,min(bottom-50,y+dy))
        position(self.root,w,h,x,y)

    def end_drag(self,event=None):
        if self.drag_start is None:return
        resizing=self.drag_start[-1];self.drag_start=None
        if self.floating:return
        if resizing:self.preferences.setdefault('page_heights',{})[self.page_key()]=self.root.winfo_height()
        self.preferences['geometry']=[self.root.winfo_width(),self.root.winfo_height(),self.root.winfo_x(),self.root.winfo_y()]
        try:save_preferences(self.settings_path,self.preferences)
        except OSError:pass

    def toggle_float(self):
        x,y=self.root.winfo_x(),self.root.winfo_y()
        anchor_bottom=y+self.root.winfo_height()
        if not self.floating:self.expanded_size=(self.root.winfo_width(),self.root.winfo_height())
        self.floating=not self.floating
        self.root.attributes('-topmost',self.floating or self.preferences['topmost'])
        self.render()
        w,h=(128,34) if self.floating else (self.expanded_size or (380,400))
        left,top,right,bottom=work_area(self.root)
        x=max(left,min(right-w,x));y=max(top,min(bottom-h,anchor_bottom-h))
        position(self.root,w,h,x,y)
        if not self.floating and self.preferences.get('view_mode','compact')=='workspace':
            self.workspace_placed=False;self.place()
        if not self.floating and self.preferences.get('view_mode','compact')!='workspace':
            self.preferences['geometry']=[w,h,x,y]
            try:save_preferences(self.settings_path,self.preferences)
            except OSError:pass

    def enter(self,event=None):
        if self.compact:
            if self.fade_job is not None:self.root.after_cancel(self.fade_job);self.fade_job=None
            self.root.attributes('-alpha',1.0 if self.preferences['hover'] else self.preferences['opacity']/100)

    def leave(self,event=None):
        if self.compact:
            if self.fade_job is not None:self.root.after_cancel(self.fade_job)
            self.fade_job=self.root.after(120,self.fade)

    def fade(self):
        self.fade_job=None
        if not self.compact:return
        x,y=self.root.winfo_pointerxy()
        inside=(self.root.winfo_rootx()<=x<self.root.winfo_rootx()+self.root.winfo_width()
                and self.root.winfo_rooty()<=y<self.root.winfo_rooty()+self.root.winfo_height())
        self.root.attributes('-alpha',1.0 if inside and self.preferences['hover'] else self.preferences['opacity']/100)

    def place(self,center=False):
        if self.floating:return
        if not self.compact:
            left,top,right,bottom=work_area(self.root)
            if not getattr(self,'workspace_placed',False):
                width=min(1440,right-left-32);height=min(920,bottom-top-48)
                position(self.root,width,height,left+16,top+16);self.workspace_placed=True
            return
        self.workspace_placed=False
        self.root.update_idletasks()
        left,top,right,bottom=work_area(self.root)
        width=max(round(380*self.preferences['size']/100),self.frame.winfo_reqwidth())
        requested=self.frame.winfo_reqheight()
        if not self.preferences.get('lock_position',False):requested=self.preferences.get('page_heights',{}).get(self.page_key(),requested)
        height=min(max(220,requested),bottom-top-50)
        width=min(width,right-left-32)
        if self.compact:
            if 'geometry' in self.preferences:
                width,_,x,y=self.preferences['geometry']
                vl,vt,vr,vb=virtual_area(self.root)
                if vl<=x<vr and vt<=y<vb:
                    position(self.root,width,height,x,y);left,top,right,bottom=work_area(self.root)
                width=min(width,right-left-32);height=min(height,bottom-top-32)
                x=max(left,min(right-width,x))
                if self.preferences.get('lock_position',False):
                    # Keep the saved anchor; grow upwards only when the lower edge
                    # would leave the work area. Collapsing returns to the saved y.
                    y=max(top,min(bottom-height,y))
                else:y=max(top,min(bottom-height,y))
            else:x,y=max(left,right-width-16),top+16
        elif center:x,y=left+max(0,(right-left-width)//2),top+max(0,(bottom-top-height)//2)
        else:x,y=self.root.winfo_x(),self.root.winfo_y()
        position(self.root,width,height,x,y)

    def customize(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift();return
        if self.root.grab_current() is not None:return
        before=dict(self.preferences)
        window=tk.Toplevel(self.root,show_on_create=False);self.settings_window=window
        window.title('화면 및 사용자 설정');window.transient(self.root)
        window.attributes('-topmost',True)
        from ui_theme import dark_titlebar
        dark_titlebar(window)
        body=ttk.Frame(window,padding=20);body.pack(fill='both',expand=True)
        actions=ttk.Frame(body);actions.pack(side='bottom',fill='x',pady=(14,0))
        ttk.Label(body,text='화면 및 사용자 설정',style='Section.TLabel').pack(anchor='w')
        settings_content=ttk.Frame(body);settings_content.pack(fill='both',expand=True)
        layout=tk.W.QHBoxLayout(settings_content._q);layout.setContentsMargins(0,0,0,0);layout.setSpacing(20)
        sidebar=ttk.Frame(settings_content);sidebar._q.setFixedWidth(140);layout.addWidget(sidebar._q)
        pages=ttk.Frame(settings_content);pages._q.setMinimumSize(460,390);scroll=tk.W.QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(tk.W.QFrame.Shape.NoFrame);scroll.setWidget(pages._q);layout.addWidget(scroll,1)
        sidebar._q.show();pages._q.show()
        sections={name:ttk.Frame(pages) for name in ('화면·글꼴','창·플로팅')}
        selected_section=tk.StringVar(value='화면·글꼴')
        def select_section():
            for name,section in sections.items():
                if name==selected_section.get():section.pack(fill='both',expand=True)
                else:section.pack_forget()
        for name in sections:
            ttk.Radiobutton(sidebar,text=name,variable=selected_section,value=name,command=select_section,style='Toolbutton').pack(fill='x',pady=(0,6))
        select_section()
        appearance_panel=sections['화면·글꼴'];window_panel=sections['창·플로팅']
        opacity=tk.DoubleVar(value=before['opacity']);size=tk.DoubleVar(value=before['size']);hover=tk.BooleanVar(value=before['hover']);topmost=tk.BooleanVar(value=before['topmost'])
        locked=tk.BooleanVar(value=before.get('lock_position',False))
        view_mode=tk.StringVar(value=before.get('view_mode','compact'))
        theme=tk.StringVar(value='화이트' if before['theme']=='light' else '다크')
        font=tk.StringVar(value=before['font'])
        chart_font=tk.StringVar(value=before.get('chart_font') or '화면 글꼴과 동일')
        numeric_font=tk.StringVar(value=before.get('numeric_font') or '화면 글꼴과 동일')
        installed=list(tk.font.families(self.root))
        registered=list(before.get('registered_fonts',[]))
        # Migrate the old bug that persisted the entire installed font catalogue.
        if set(registered)==set(installed):registered=[]
        for name in (before['font'],before.get('chart_font'),before.get('numeric_font')):
            if name and name not in registered:registered.append(name)
        registered=sorted(set(registered),key=str.casefold)
        text_scale=tk.DoubleVar(value=before.get('text_scale',110))
        text_sizes={key:tk.DoubleVar(value=before.get('text_sizes',{}).get(key,before.get('text_scale',110)/10)) for key in ('system','description','data')}
        labels=[tk.StringVar(),tk.StringVar(),tk.StringVar()]
        preview_job=None;finishing=False
        def apply_preview():
            nonlocal preview_job
            preview_job=None
            previous_size=self.preferences['size']
            if self.compact and locked.get() and not self.preferences.get('lock_position',False):
                self.preferences['geometry']=[self.root.winfo_width(),self.root.winfo_height(),self.root.winfo_x(),self.root.winfo_y()]
            self.preferences.update(text_sizes={key:var.get() for key,var in text_sizes.items()},text_scale=round(text_sizes['system'].get()*10),numeric_font='' if numeric_font.get()=='화면 글꼴과 동일' else numeric_font.get(),registered_fonts=list(registered),opacity=round(opacity.get()),size=round(size.get()),hover=hover.get(),topmost=topmost.get(),lock_position=locked.get(),theme='light' if theme.get()=='화이트' else 'dark',font=font.get(),chart_font='' if chart_font.get()=='화면 글꼴과 동일' else chart_font.get())
            from appearance import set_appearance
            set_appearance(self.root,self.preferences['theme'],self.preferences['font'],self.preferences.get('chart_font',''),self.preferences.get('numeric_font',''),self.preferences.get('text_scale',110),self.preferences.get('text_sizes'))
            if previous_size!=self.preferences['size']:
                if not self.preferences.get('lock_position',False):self.preferences.pop('geometry',None)
                self.preferences.pop('page_heights',None)
            labels[0].set(f"투명도 {100-self.preferences['opacity']}% · 0%이면 완전히 선명")
            labels[2].set(f"텍스트 크기 {self.preferences['text_scale']}%")
            labels[1].set(f"메뉴 크기 {self.preferences['size']}%")
            if previous_size!=self.preferences['size']:
                self.render();self.place()
            self.root.attributes('-topmost',self.floating or self.preferences['topmost'])
            self.root.attributes('-alpha',self.preferences['opacity']/100 if self.compact else 1.0)
        def preview(*_):
            nonlocal preview_job
            if finishing:return
            if preview_job is not None:window.after_cancel(preview_job)
            preview_job=window.after(100,apply_preview)
        ttk.Label(window_panel,text='프로그램 사용 모드',style='Accent.TLabel').pack(anchor='w',pady=(0,8))
        for caption,value in (('작은 창','compact'),('전체 창 · 여러 작업 탭','workspace')):
            ttk.Radiobutton(window_panel,text=caption,variable=view_mode,value=value,command=preview).pack(anchor='w')
        ttk.Label(window_panel,text='사용 모드 변경은 저장 후 적용됩니다.',style='Muted.TLabel').pack(anchor='w',pady=6)
        appearance_row=ttk.Frame(appearance_panel);appearance_row.pack(fill='x',pady=8)
        ttk.Label(appearance_row,text='화면 테마').pack(side='left')
        for label in ('다크','화이트'):
            ttk.Radiobutton(appearance_row,text=label,variable=theme,value=label,command=preview).pack(side='left',padx=8)
        font_row=ttk.Frame(appearance_panel);font_row.pack(fill='x',pady=6)
        ttk.Label(font_row,text='글꼴').pack(side='left',padx=(0,12))
        families=registered
        font_box=ttk.Combobox(font_row,textvariable=font,values=families,width=28,state='readonly');font_box.pack(side='left');font_box._q.setAccessibleName('화면 글꼴')
        font_box.bind('<<ComboboxSelected>>',preview)
        chart_row=ttk.Frame(appearance_panel);chart_row.pack(fill='x',pady=6)
        ttk.Label(chart_row,text='그래프 글꼴').pack(side='left',padx=(0,12))
        chart_box=ttk.Combobox(chart_row,textvariable=chart_font,values=['화면 글꼴과 동일']+families,width=28,state='readonly');chart_box.pack(side='left');chart_box._q.setAccessibleName('그래프 글꼴')
        chart_box.bind('<<ComboboxSelected>>',preview)
        number_row=ttk.Frame(appearance_panel);number_row.pack(fill='x',pady=6)
        ttk.Label(number_row,text='숫자 글꼴').pack(side='left',padx=(0,12))
        number_box=ttk.Combobox(number_row,textvariable=numeric_font,values=['화면 글꼴과 동일']+registered,width=28,state='readonly');number_box.pack(side='left');number_box._q.setAccessibleName('숫자 글꼴')
        number_box.bind('<<ComboboxSelected>>',preview)
        def register_font():
            from font_picker import open_font_picker
            def added(name):
                if name not in registered:registered.append(name)
                registered.sort(key=str.casefold)
                font_box.configure(values=registered)
                for box in (chart_box,number_box):box.configure(values=['화면 글꼴과 동일']+registered)
                font.set(name)
                preview()
            open_font_picker(window,added)
        ttk.Button(appearance_panel,text='글꼴 추가',command=register_font).pack(anchor='w',pady=8)
        def number_setting(panel,caption,var,low,high,suffix):
            row=ttk.Frame(panel);row.pack(fill='x',pady=5)
            layout=tk.W.QHBoxLayout(row._q);layout.setContentsMargins(0,0,0,0)
            layout.addWidget(tk.W.QLabel(caption));layout.addStretch()
            control=tk.W.QDoubleSpinBox();control.setRange(low,high);control.setDecimals(0 if suffix==' %' else 1);control.setSingleStep(1 if suffix==' %' else .5)
            control.setSuffix(suffix);control.setValue(var.get());control.setAccessibleName(caption);control.setMinimumWidth(115);control.setSizePolicy(tk.W.QSizePolicy.Policy.Minimum,tk.W.QSizePolicy.Policy.Fixed);control.setKeyboardTracking(False)
            layout.addWidget(control)
            def changed(value):var.set(value);preview()
            control.valueChanged.connect(changed)
            def update(*args):
                with tk.C.QSignalBlocker(control):control.setValue(var.get())
            var.trace_add('write',update)
        number_setting(window_panel,'투명도',opacity,30,100,' %')
        number_setting(appearance_panel,'메뉴 크기',size,75,130,' %')
        for key,caption in [('system','시스템 제목 및 메뉴'),('description','메뉴 안 설명'),('data','실제 데이터')]:
            number_setting(appearance_panel,caption,text_sizes[key],8,28,' pt')
        ttk.Label(window_panel,text='투명도는 투명화 모드에서 적용됩니다.',style='Muted.TLabel').pack(anchor='w',pady=8)
        ttk.Checkbutton(window_panel,text='마우스를 올리면 선명하게 표시',variable=hover,command=preview).pack(anchor='w')
        ttk.Checkbutton(window_panel,text='일반 메뉴를 항상 맨 위에 표시 (플로팅은 항상 위)',variable=topmost,command=preview).pack(anchor='w',pady=(6,0))
        ttk.Checkbutton(window_panel,text='지금 위치에 고정 (마우스 이동 잠금)',variable=locked,command=preview).pack(anchor='w',pady=(6,0))
        def finish(save):
            nonlocal preview_job,finishing
            if finishing:return
            finishing=True
            if preview_job is not None:window.after_cancel(preview_job);preview_job=None
            applied_size=self.preferences['size'];applied_mode=self.preferences.get('view_mode','compact')
            if save:
                apply_preview()
                self.preferences['view_mode']=view_mode.get()
                try:save_preferences(self.settings_path,self.preferences)
                except OSError as e:
                    finishing=False;messagebox.showerror('설정 저장 실패',str(e),parent=window);return
            else:
                for key in ('favorite_workflows','recent_workflows'):
                    if key in self.preferences:before[key]=self.preferences[key]
                self.preferences=before
            from appearance import set_appearance
            set_appearance(self.root,self.preferences['theme'],self.preferences['font'],self.preferences.get('chart_font',''),self.preferences.get('numeric_font',''),self.preferences.get('text_scale',110),self.preferences.get('text_sizes'))
            window.destroy();self.settings_window=None
            self.root.attributes('-topmost',self.floating or self.preferences['topmost'])
            if applied_size!=self.preferences['size'] or applied_mode!=self.preferences.get('view_mode','compact'):
                self.render();self.place()
            self.fade() if self.compact else None
        def reset():
            [var.set(11) for var in text_sizes.values()];view_mode.set(DEFAULTS['view_mode']);opacity.set(DEFAULTS['opacity']);size.set(DEFAULTS['size']);text_scale.set(DEFAULTS['text_scale']);hover.set(DEFAULTS['hover']);topmost.set(DEFAULTS['topmost']);locked.set(False);theme.set('화이트' if DEFAULTS['theme']=='light' else '다크');font.set(DEFAULTS['font']);chart_font.set('화면 글꼴과 동일');numeric_font.set('화면 글꼴과 동일');preview()
        ttk.Button(actions,text='초기값',command=reset).pack(side='left')
        ttk.Button(actions,text='취소',command=lambda:finish(False)).pack(side='left',padx=(18,0))
        ttk.Button(actions,text='저장',command=lambda:finish(True),style='Primary.TButton').pack(side='right')
        window.protocol('WM_DELETE_WINDOW',lambda:finish(False));window.bind('<Escape>',lambda e:finish(False))
        apply_preview();window.update_idletasks()
        left,top,right,bottom=work_area(self.root)
        width=min(820,right-left-40);height=min(670,bottom-top-60)
        window.geometry(f'{width}x{height}+{left+max(0,(right-left-width)//2)}+{top+max(0,(bottom-top-height)//2)}')
        window.grab_set()
