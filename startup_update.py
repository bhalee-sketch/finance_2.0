"""Nonblocking startup updates: read-only status and one-time non-modal credential binding."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import qt_ui as tk
from release_update import GithubClient,GithubAccessError,download_setup,install_root,latest_setup,prepare_release,release_metadata,UpdateError
from token_store import load_update_token as load_token
from version_status import version_status


def check_on_start(root):
    if getattr(root,'_update_check_started',False):return
    root._update_check_started=True
    from app_version import current_version
    current=current_version();status=version_status(root);folder=install_root()
    from app_profile import beta_label,source_label
    if source_label():status.set(source_label()+' · 소스 테스트 · EXE 자동 업데이트 제외');return
    if beta_label():status.set(beta_label()+' · 별도 테스트 설치본 · 자동 업데이트 제외');return
    if current is None:status.set('현재 버전 정보를 확인할 수 없습니다.');return
    if folder is None or not getattr(sys,'frozen',False):
        status.set(f'현재 {current} · 소스 실행');return
    try:
        channel=release_metadata(Path(sys.executable).parent).get('update_channel')
    except (OSError,ValueError,UpdateError):
        channel=None
    if channel=='manual':
        status.set(f'현재 {current} · 설치 파일로 업데이트');return
    if channel=='setup':
        check_for_setup(root,folder,current,status);return
    if (folder/'pending.json').exists():
        status.set(f'현재 {current} · 업데이트 적용 확인 중')
        waits=getattr(root,'_update_pending_waits',0)+1;root._update_pending_waits=waits
        if waits<=30:
            root._update_check_started=False
            root.after(1000,lambda:check_on_start(root))
        else:status.set(f'현재 {current} · 시작 확인 상태 점검 필요')
        return
    status.set(f'현재 {current} · 최신 버전 확인 중…')
    messages=queue.Queue();cancel=threading.Event()
    def destroyed(event):
        if event.widget is root:cancel.set()
    root.bind('<Destroy>',destroyed,add='+')
    def worker():
        try:
            # A private credential stays on the user's PC, never in source or binaries.
            token=os.environ.get('WORKSPACE_GITHUB_TOKEN','').strip() or load_token(folder)
            if cancel.is_set():return
            client=GithubClient(token);manifest=client.latest(current)
            if not manifest:messages.put(('latest',None));return
            messages.put(('status',f"새 버전 {manifest['version']} · 다운로드 및 검증 중…"))
            def progress(percent):
                if cancel.is_set():raise RuntimeError('Update cancelled')
                messages.put(('status',f"새 버전 {manifest['version']} · 다운로드 {percent}%"))
            prepare_release(folder,manifest,client,progress)
            messages.put(('prepared',manifest['version']))
        except GithubAccessError:
            if not cancel.is_set():messages.put(('authentication','environment' if os.environ.get('WORKSPACE_GITHUB_TOKEN','').strip() else None))
        except Exception:
            if not cancel.is_set():messages.put(('error',None))
    def poll():
        if cancel.is_set() or not root.winfo_exists():return
        try:
            while True:
                kind,value=messages.get_nowait()
                if kind=='status':status.set(value);continue
                if kind=='latest':status.set(f'현재 {current} · 최신 버전입니다.');return
                if kind=='authentication':
                    if value=='environment':
                        status.set(f'현재 {current} · WORKSPACE_GITHUB_TOKEN 환경변수의 권한·만료 확인 필요');return
                    status.set(f'현재 {current} · 자동 업데이트 인증 확인 필요')
                    from update_credentials_ui import request_credentials
                    def resume():
                        root._update_check_started=False
                        check_on_start(root)
                    request_credentials(root,resume);return
                if kind=='error':status.set(f'현재 {current} · 최신 버전 확인 불가 (연결·인증 확인)');return
                # Background checks must never discard an already opened workflow.
                windows=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and w.winfo_exists()]
                if windows:
                    status.set(f'새 버전 {value} 준비 완료 · 다음 실행 시 적용');return
                try:
                    subprocess.Popen([str(folder/'WorkSpace.exe'),'--activate',value,str(os.getpid())],cwd=folder,env=dict(os.environ,PYINSTALLER_RESET_ENVIRONMENT='1'))
                except OSError:
                    status.set(f'새 버전 {value} · 적용 실패, 현재 버전 유지');return
                root.destroy();return
        except queue.Empty:pass
        root.after(100,poll)
    # Allow the stable launcher's readiness handshake to finish before activation.
    root.after(1500,lambda:threading.Thread(target=worker,daemon=True).start())
    root.after(100,poll)


def check_for_setup(root,folder,current,status):
    from app import center_window
    from ui_theme import dark_titlebar

    status.set(f'현재 {current} · 최신 버전 확인 중…')
    messages=queue.Queue()
    dialog=tk.Toplevel(root);dialog.title('업데이트 확인');dialog.transient(root)
    center_window(dialog,450,160);dark_titlebar(dialog)
    body=tk.ttk.Frame(dialog,padding=16);body.pack(fill='both',expand=True)
    notice=tk.StringVar(value='최신 버전을 확인하고 있습니다…')
    tk.ttk.Label(body,textvariable=notice).pack(fill='x')
    progress=tk.ttk.Progressbar(body);progress.start();progress.pack(fill='x',pady=10)
    buttons=tk.ttk.Frame(body);buttons.pack(fill='x')
    update=tk.ttk.Button(buttons,text='지금 업데이트',state='disabled')
    update.pack(side='right')
    later=tk.ttk.Button(buttons,text='건너뛰기',command=dialog.destroy)
    later.pack(side='right',padx=(0,8))
    dialog.grab_set()

    def background(kind,work):
        def worker():
            try:messages.put((kind,work()))
            except (OSError,ValueError,TypeError,KeyError):messages.put(('error',None))
        threading.Thread(target=worker,daemon=True).start()
        dialog.after(120,poll)

    def begin_download(setup):
        version=setup[0]
        status.set(f'새 버전 {version} · 다운로드 및 검증 중…')
        notice.set(f'{version} 다운로드 및 검증 중…')
        update.configure(state='disabled');later.configure(text='취소')
        progress.start()
        def work():
            for path in (folder/'downloads').glob('WorkSpace-Setup-*-x64.*'):
                try:path.unlink()
                except OSError:pass
            return download_setup(folder,setup,lambda percent:messages.put(('progress',percent)))
        background('downloaded',work)

    def install(installer):
        # NSIS requires /D last and unquoted, including when the path contains spaces.
        command=subprocess.list2cmdline([str(installer),'/AUTORESTART=1',f'/WAITPID={os.getpid()}'])
        try:
            subprocess.Popen(command+' /D='+str(folder),executable=str(installer),cwd=folder)
        except OSError as exc:
            print(f'Could not start installer: {exc}',file=sys.stderr)
            notice.set('설치 프로그램을 시작하지 못했습니다.')
            update.configure(state='normal',command=lambda:install(installer))
            return
        root.destroy()

    def poll():
        try:
            while True:
                kind,value=messages.get_nowait()
                if kind=='progress':
                    progress._q.setRange(0,100);progress._q.setValue(value)
                    continue
                progress.stop()
                if kind=='checked' and value:
                    status.set(f'새 버전 {value[0]} · 업데이트 가능')
                    notice.set(f'현재 {current} · 새 버전 {value[0]}')
                    update.configure(state='normal',command=lambda:begin_download(value))
                    later.configure(text='나중에')
                elif kind=='checked':
                    status.set(f'현재 {current} · 최신 버전입니다.')
                    notice.set('현재 최신 버전을 사용하고 있습니다.')
                    dialog.after(500,dialog.destroy)
                elif kind=='downloaded':
                    status.set('업데이트 설치 및 재시작 중…')
                    notice.set('검증 완료 · 설치를 위해 Work Space를 다시 시작합니다.')
                    dialog.after_idle(lambda:install(value))
                else:
                    status.set(f'현재 {current} · 업데이트 확인 또는 다운로드 불가')
                    notice.set('업데이트를 확인하거나 다운로드하지 못했습니다.')
                    later.configure(text='닫기')
                return
        except queue.Empty:
            dialog.after(120,poll)

    background('checked',lambda:latest_setup(current))
