"""Four-part desktop shell: top tabs, list sidebar, work area and status bar."""
from pathlib import Path
import re
import qt_ui as tk
from qt_ui import ttk

C,G,W=tk.C,tk.G,tk.W


class SidebarDelegate(W.QStyledItemDelegate):
    def paint(self,painter,option,index):
        option=W.QStyleOptionViewItem(option)
        option.state &= ~W.QStyle.StateFlag.State_HasFocus
        super().paint(painter,option,index)


class Workspace:
    def __init__(self,launcher):
        self.launcher=launcher;self.root=launcher.root;self.tabs={};self.closing={}
        self.commands={};self.categories={};self._syncing=False
        self.frame=ttk.Frame(self.root)
        self.frame._q.setObjectName('WorkspaceChrome')
        outer=W.QVBoxLayout(self.frame._q);outer.setContentsMargins(10,8,10,6);outer.setSpacing(8)

        top=W.QFrame();top.setObjectName('WorkspaceTopbar');top.setMinimumHeight(44)
        row=W.QHBoxLayout(top);row.setContentsMargins(2,0,2,0);row.setSpacing(8)
        self.home_button=W.QToolButton();self.home_button.setObjectName('WorkspaceHomeButton')
        self.home_button.setCheckable(True);self.home_button.setFixedSize(36,36);self.home_button.setIconSize(C.QSize(28,28))
        icon=G.QIcon(str(Path(__file__).resolve().parent/'assets'/'home.svg'))
        if icon.isNull():self.home_button.setText('W')
        else:self.home_button.setIcon(icon)
        self.home_button.setToolTip('홈');self.home_button.setAccessibleName('홈')
        self.home_button.clicked.connect(self.go_home);row.addWidget(self.home_button)
        self.top_tabs=W.QTabBar();self.top_tabs.setObjectName('WorkspaceTabs')
        self.top_tabs.setExpanding(False);self.top_tabs.setUsesScrollButtons(True)
        self.top_tabs.setMinimumWidth(0)
        self.top_tabs.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Fixed)
        self.top_tabs.setElideMode(C.Qt.TextElideMode.ElideRight);self.top_tabs.setTabsClosable(False)
        self.top_tabs.setDocumentMode(True);self.top_tabs.setDrawBase(False);row.addWidget(self.top_tabs,1,C.Qt.AlignmentFlag.AlignBottom)
        self.local_badge=W.QLabel('●  로컬 실행');self.local_badge.setObjectName('WorkspaceLocalBadge')
        self.local_badge.setSizePolicy(W.QSizePolicy.Policy.Fixed,W.QSizePolicy.Policy.Fixed);row.addWidget(self.local_badge)
        for text,tip,command in [('플로팅','작은 플로팅 메뉴로 전환',launcher.toggle_float),('설정','화면 · 글꼴 · 창 설정',launcher.customize)]:
            b=W.QToolButton();b.setText(text);b.setToolTip(tip);b.setAccessibleName(text)
            if text=='설정':
                b.setIcon(G.QIcon(str(Path(__file__).resolve().parent/'assets'/'settings.svg')));b.setIconSize(C.QSize(22,22));b.setToolButtonStyle(C.Qt.ToolButtonStyle.ToolButtonIconOnly)
            b.clicked.connect(lambda checked=False,fn=command:fn());row.addWidget(b)
        outer.addWidget(top)

        self.layout=ttk.Panedwindow(self.frame,orient='horizontal')
        self.layout._q.setObjectName('WorkspaceSplit');self.layout._q.setHandleWidth(2);self.layout._q.setChildrenCollapsible(False)
        outer.addWidget(self.layout._q,1);self.layout._q.show()
        self.side=W.QFrame();self.side.setObjectName('WorkspaceSidebar');self.side.setFixedWidth(200)
        side_layout=W.QVBoxLayout(self.side);side_layout.setContentsMargins(8,10,3,8);side_layout.setSpacing(8)
        caption=W.QLabel('Work Space');caption.setObjectName('WorkspaceSection');side_layout.addWidget(caption)
        self.nav=ttk.NavigationTree(self.frame,show='tree',selectmode='browse')
        self.nav._q.setObjectName('WorkspaceNavigation');self.nav._q.setMinimumWidth(0);self.nav._q.setRootIsDecorated(False);self.nav._q.setItemsExpandable(False);self.nav._q.setExpandsOnDoubleClick(False);self.nav._q.setIndentation(12)
        self.nav._q.setItemDelegate(SidebarDelegate(self.nav._q))
        side_layout.addWidget(self.nav._q,1);self.nav._q.show()
        for gi,(name,cards) in enumerate(launcher.groups):
            group=self.nav.insert('','end',iid=f'g{gi}',text=re.sub(r'^\d+\.\s*','',name),open=True)
            icons=('statements','analysis','tools','funds','merge','statements')
            if gi<len(icons):self.nav._nodes[group].setIcon(G.QIcon(str(Path(__file__).resolve().parent/'assets'/('menu-'+icons[gi]+'.svg'))))
            for ci,(label,command) in enumerate(cards):
                key=f'g{gi}c{ci}';title=label.split('\n')[0]
                self.nav.insert(group,'end',iid=key,text=title)
                self.commands[key]=(title,command);self.categories[key]=name
        self.layout._q.addWidget(self.side)

        self.notebook=ttk.Notebook(self.frame)
        self.notebook._q.setObjectName('WorkspacePages');self.notebook._q.tabBar().hide()
        self.layout._q.addWidget(self.notebook._q);self.notebook._q.show();self.layout._q.setStretchFactor(0,0);self.layout._q.setStretchFactor(1,1);self.layout._q.setSizes([200,1100])
        self.home=ttk.Frame(self.notebook);self.home._q.setObjectName('WorkspaceHomePanel')
        home_layout=W.QVBoxLayout(self.home._q);home_layout.setContentsMargins(0,0,0,0)
        home_layout.addStretch()
        self.notebook.add(self.home,text='홈')

        footer=W.QFrame();footer.setObjectName('WorkspaceStatusbar');footer.setMinimumHeight(28)
        status_layout=W.QHBoxLayout(footer);status_layout.setContentsMargins(4,0,4,0)
        self.status=tk.StringVar(value='준비');self.status_label=W.QLabel('준비');self.status_label.setObjectName('WorkspaceMuted')
        self.status.trace_add('write',lambda *_:self.status_label.setText(self.status.get()))
        status_layout.addWidget(self.status_label,1)
        self.detail_label=W.QLabel();self.detail_label.setObjectName('WorkspaceMuted');self.detail_label.setMaximumWidth(320);status_layout.addWidget(self.detail_label)
        version=W.QLabel();version.setObjectName('WorkspaceMuted');status_layout.addWidget(version)
        from version_status import bind_status_label
        bind_status_label(self.root,version)
        outer.addWidget(footer)

        # Arrow keys select; only explicit activation opens a workflow.
        self.nav._q.clicked.connect(lambda _:self.selected())
        self.nav._q.activated.connect(lambda _:self.selected())
        self.shortcuts=[]
        for keys,command in [('Ctrl+Tab',lambda:self.cycle_tab(1)),('Ctrl+Shift+Tab',lambda:self.cycle_tab(-1)),('Ctrl+W',self.close_tab),('Home',self.go_home)]:
            shortcut=G.QShortcut(G.QKeySequence(keys),self.frame._q);shortcut.activated.connect(command);self.shortcuts.append(shortcut)
        self.notebook.bind('<<NotebookTabChanged>>',lambda event:self.sync_tabs())
        self.top_tabs.currentChanged.connect(self.activate_top_tab)
        self.top_tabs.tabBarClicked.connect(self.activate_top_tab)
        self.top_tabs.tabCloseRequested.connect(self.close_index)
        self.sync_tabs()

    def sync_tabs(self):
        if self._syncing or not self.frame.winfo_exists():return
        self._syncing=True
        try:
            previous=getattr(self,'tab_paths',[])
            self.tab_paths=[path for path in self.notebook.tabs() if path!=str(self.home)]
            current=self.notebook.select()
            self.top_tabs.blockSignals(True)
            if previous!=self.tab_paths or self.top_tabs.count()!=len(self.tab_paths):
                while self.top_tabs.count():self.top_tabs.removeTab(0)
                for path in self.tab_paths:
                    title=self.notebook.tab(path,'text');index=self.top_tabs.addTab(title)
                    self.top_tabs.setTabToolTip(index,title)
                    close=W.QToolButton();close.setText('×');close.setToolTip(title+' 닫기');close.setObjectName('WorkspaceTabClose');close.setFixedSize(22,22);close.setIcon(G.QIcon(str(Path(__file__).resolve().parent/'assets'/'close.svg')));close.setIconSize(C.QSize(16,16));close.setToolButtonStyle(C.Qt.ToolButtonStyle.ToolButtonIconOnly)
                    close.clicked.connect(lambda checked=False,p=path:self.close_index(self.tab_paths.index(p)) if p in self.tab_paths else None)
                    self.top_tabs.setTabButton(index,W.QTabBar.ButtonPosition.RightSide,close)
            if current in self.tab_paths:self.top_tabs.setCurrentIndex(self.tab_paths.index(current))
            self.top_tabs.blockSignals(False)
            self.side.show()
            self.update_status()
        finally:self._syncing=False

    def activate_top_tab(self,index):
        if not self._syncing and 0<=index<len(self.tab_paths):self.notebook.select(self.tab_paths[index])

    def update_status(self):
        if not hasattr(self,'status'):return
        current=self.notebook.select()
        home_active=current==str(self.home)
        self.home_button.setChecked(home_active)
        if self.top_tabs.property('homeActive')!=home_active:
            self.top_tabs.setProperty('homeActive',home_active)
            self.top_tabs.style().unpolish(self.top_tabs);self.top_tabs.style().polish(self.top_tabs)
        if home_active:
            self.status.set('홈')
            self.bind_work_status(None)
            self.detail_label.setToolTip('')
            self.detail_label.setText(f'열린 작업 {sum(w.winfo_exists() for w in self.tabs.values())}개')
        elif current:
            self.status.set('현재 작업 · '+self.notebook.tab(current,'text'))
            window=self.root.nametowidget(current)
            self.bind_work_status(getattr(window,'_work_status',None))
            if getattr(window,'_work_status',None) is None:self.detail_label.setText('처리 · 저장 상태는 업무 화면에서 확인')

    def bind_work_status(self,variable):
        old=getattr(self,'_work_status_binding',None)
        if old and old[0] is variable:return
        if old:old[0].trace_remove('write',old[1])
        self._work_status_binding=None
        if variable is None:return
        def display(*_):
            if not self.frame.winfo_exists():return
            text=variable.get();self.detail_label.setToolTip(text)
            self.detail_label.setText(self.detail_label.fontMetrics().elidedText(text,C.Qt.TextElideMode.ElideRight,310))
        token=variable.trace_add('write',display);self._work_status_binding=(variable,token);display()

    def save_discovery(self):
        from launcher import save_preferences
        try:save_preferences(self.launcher.settings_path,self.launcher.preferences)
        except OSError:self.status.set('업무 목록 설정을 저장하지 못했습니다. 현재 실행에는 적용됩니다.')

    def remember_workflow(self,title):
        values=self.launcher.preferences.get('recent_workflows',[])
        self.launcher.preferences['recent_workflows']=[title]+[v for v in values if v!=title][:18]
        self.save_discovery()

    def go_home(self):
        if self.root.grab_current() is not None:return
        self.notebook.select(self.home)
        pending=list(self.tabs.values())
        def close_all():
            if not self.frame.winfo_exists():return
            remaining=[]
            for window in pending:
                if not window.winfo_exists():continue
                callback=self.closing.get(str(window))
                if callback:callback()
                else:window.destroy()
                if window.winfo_exists():remaining.append(window)
                else:
                    if tk.isValid(window._q):self.notebook.forget(window)
                    self.tabs={key:w for key,w in self.tabs.items() if w is not window};self.closing.pop(str(window),None)
            pending[:]=remaining;self.sync_tabs()
            if pending:
                self.status.set('홈 · 처리 중인 작업은 완료 후 자동으로 닫습니다.')
                self.root.after(250,close_all)
        close_all()

    def cycle_tab(self,offset):
        if self.root.grab_current() is not None:return
        count=self.top_tabs.count()
        if count:
            index=(self.top_tabs.currentIndex()+offset)%count
            self.top_tabs.setCurrentIndex(index);self.activate_top_tab(index)

    def show(self):self.frame.pack(fill='both',expand=True)
    def hide(self):self.frame.pack_forget()

    def selected(self,event=None):
        selected=self.nav.selection()
        if not selected:return
        key=selected[0]
        if key in self.commands:self.open(key)

    def open(self,key):
        if self.root.grab_current() is not None:return
        if key in self.tabs and self.tabs[key].winfo_exists():self.notebook.select(self.tabs[key]);self.remember_workflow(self.commands[key][0]);return
        title,command=self.commands[key];before=set(self.root.winfo_children())
        with tk.defer_workflow_windows(self.root):
            command()
            windows=[w for w in self.root.winfo_children() if w not in before and isinstance(w,tk.Toplevel)]
            if not windows:return
            window=windows[0]
            if not window.winfo_exists() or self.root.grab_current() is not None:return
            callback=window.protocol('WM_DELETE_WINDOW')
            window.withdraw();window._q.setWindowFlag(C.Qt.WindowType.Window,False)
            self.tabs[key]=window;self.closing[str(window)]=callback
            self.notebook.add(window,text=title);self.notebook.select(window)
            self.remember_workflow(title);self.sync_tabs()

    def close_index(self,index):
        if index<0 or index>=len(self.tab_paths):return
        self.notebook.select(self.tab_paths[index]);self.close_tab()

    def close_tab(self):
        selected=self.notebook.select()
        if not selected or selected==str(self.home) or self.root.grab_current() is not None:return
        window=self.root.nametowidget(selected);callback=self.closing.get(selected)
        if callback:callback()
        else:window.destroy()
        if window.winfo_exists():self.status.set('작업 중인 화면입니다. 작업 완료 또는 중단 후 닫으세요.')
        else:
            if tk.isValid(window._q):self.notebook.forget(window)
            self.tabs={k:w for k,w in self.tabs.items() if str(w)!=selected};self.closing.pop(selected,None)
            self.sync_tabs()
