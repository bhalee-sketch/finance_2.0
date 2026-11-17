"""Shared non-modal progress window for background work and staged rendering."""
import qt_ui as tk
from qt_ui import ttk
from ui_theme import dark_titlebar


def center_loading_window(loading,owner):
    """Size the dialog explicitly before centering over an embedded or standalone view."""
    loading.update_idletasks()
    rect=owner._q.rect()
    center=owner._q.mapToGlobal(rect.center())
    screen=tk.application().screenAt(center) or owner._q.screen()
    available=screen.availableGeometry()
    width=min(max(420,loading.winfo_reqwidth()+16),available.width()-24)
    height=min(max(170,loading.winfo_reqheight()+16),available.height()-24)
    x=max(available.left()+12,min(center.x()-width//2,available.right()-width-11))
    y=max(available.top()+12,min(center.y()-height//2,available.bottom()-height-11))
    loading.geometry(f'{width}x{height}{x:+d}{y:+d}')
    loading._q.setFixedSize(width,height)


class LoadingIndicator:
    def __init__(self,owner,status):
        self.owner=owner;self.status=status;self.dialog=None;self.timer=None;self.active=False
    def start(self):
        if self.active:return
        self.active=True
        self.timer=self.owner.after(120,self.show)
    def show(self):
        self.timer=None
        if not self.active or not self.owner.winfo_exists():return
        dialog=tk.Toplevel(self.owner,show_on_create=False);self.dialog=dialog
        dialog.title('자료 처리 중');dialog.transient(self.owner);dark_titlebar(dialog)
        dialog._q.setAttribute(tk.C.Qt.WidgetAttribute.WA_ShowWithoutActivating,True)
        dialog.protocol('WM_DELETE_WINDOW',lambda:None)
        panel=ttk.Frame(dialog,padding=24);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='자료를 처리하고 있습니다',style='Section.TLabel').pack(anchor='w')
        ttk.Label(panel,textvariable=self.status,wraplength=400,style='Muted.TLabel').pack(fill='x',pady=(8,14))
        self.progress=ttk.Progressbar(panel,mode='indeterminate',length=360)
        self.progress.pack(fill='x');self.progress.start(12)
        center_loading_window(dialog,self.owner);dialog.deiconify()
    def close(self):
        self.active=False
        if self.timer is not None:
            if self.owner.winfo_exists():self.owner.after_cancel(self.timer)
            self.timer=None
        if self.dialog is not None:
            if self.dialog.winfo_exists():self.progress.stop();self.dialog.destroy()
            self.dialog=None


def watch_loading(window,status,is_busy):
    """Observe legacy worker state on the GUI thread, independent of status wording."""
    indicator=LoadingIndicator(window,status)
    def poll():
        if not window.winfo_exists():indicator.close();return
        if is_busy():indicator.start()
        else:indicator.close()
        window.after(50,poll)
    window.after(0,poll)
    return indicator
