"""Frozen application entry point; user workbooks remain in their existing locations."""
import os
from pathlib import Path
import sys
import traceback

def report_duplicate(root):
    """Also acknowledge an older launcher's ready protocol to avoid false rollback."""
    import qt_ui as tk
    from qt_ui import messagebox
    import time
    marker=os.environ.get('WORKSPACE_READY_FILE')
    dialog=tk.Tk();dialog.withdraw()
    try:
        if marker and not (root/'pending.json').exists():
            from update_ui import signal_ready
            signal_ready()
        messagebox.showinfo('Work Space','이미 실행 중입니다. 기존 메뉴 창 또는 플로팅을 확인하세요.',parent=dialog)
        if marker:
            deadline=time.monotonic()+5
            while Path(marker).exists() and time.monotonic()<deadline:time.sleep(.1)
    finally:dialog.destroy()


def redirect_to_active(root):
    """Direct shortcuts to a different version follow the validated launcher pointer."""
    if not getattr(sys,'frozen',False) or os.environ.get('WORKSPACE_READY_FILE') or (root/'pending.json').exists():return False
    from release_update import current_state,release_path,release_metadata
    active=release_path(root,current_state(root)['current'])
    if Path(sys.executable).resolve().parent==active.resolve():return False
    release_metadata(active)
    launcher=root/'WorkSpace.exe'
    if not launcher.is_file():raise ValueError('Work Space 실행기를 찾을 수 없습니다. 설치 파일로 복구하세요.')
    import subprocess
    subprocess.Popen([str(launcher)],cwd=root,env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1'))
    return True


def main():
    from taskbar_identity import set_taskbar_identity
    set_taskbar_identity()
    from installed_launcher import single_instance
    from release_update import install_root
    root=install_root()
    if root is None:root=Path(sys.executable).resolve().parents[2];os.environ['WORKSPACE_INSTALL_ROOT']=str(root)
    if redirect_to_active(root):return
    if not single_instance(root,'application'):
        report_duplicate(root);return
    def fix_shortcuts():
        try:
            from shortcut_repair import repair_shortcuts
            repair_shortcuts(root)
        except Exception:pass  # Shortcut repair must never prevent application startup.
    import threading
    threading.Thread(target=fix_shortcuts,daemon=True).start()
    logdir=root/'logs';logdir.mkdir(parents=True,exist_ok=True)
    with (logdir/'app.log').open('a',encoding='utf-8',buffering=1) as log:
        sys.stdout=sys.stderr=log
        import qt_ui as tk
        from qt_ui import messagebox
        def failed(kind,value,tb):
            traceback.print_exception(kind,value,tb,file=log)
            messagebox.showerror('Work Space 오류',f'{value}\n\n오류 기록: {logdir / "app.log"}')
        tk.Tk.report_callback_exception=lambda self,*args:failed(*args)
        try:
            from app import main as run
            run()
        except Exception:failed(*sys.exc_info())

if __name__=='__main__':main()
