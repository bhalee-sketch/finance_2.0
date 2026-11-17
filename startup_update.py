"""Nonblocking startup updates: read-only status and one-time non-modal credential binding."""
import os
import queue
import subprocess
import sys
import threading
import qt_ui as tk
from release_update import GithubClient,GithubAccessError,install_root,prepare_release
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
