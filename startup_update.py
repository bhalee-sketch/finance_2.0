"""Check for a Windows Setup release and download it in the open update dialog."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import qt_ui as tk
from release_update import GITHUB_HOSTS, MAX_ARCHIVE, SETUP_API, UpdateError, install_root, latest_setup, release_metadata
from version_status import version_status


def check_on_start(root):
    if getattr(root, '_update_check_started', False):
        return
    root._update_check_started = True
    from app_profile import beta_label, source_label
    from app_version import current_version

    current = current_version()
    folder = install_root()
    status = version_status(root)
    if source_label():
        status.set(source_label() + ' · 소스 테스트 · EXE 자동 업데이트 제외')
    elif beta_label():
        status.set(beta_label() + ' · 별도 테스트 설치본 · 자동 업데이트 제외')
    elif current is None:
        status.set('현재 버전 정보를 확인할 수 없습니다.')
    elif folder is None or not getattr(sys, 'frozen', False):
        status.set(f'현재 {current} · 소스 실행')
    else:
        try:
            channel = release_metadata(Path(sys.executable).parent).get('update_channel')
        except (OSError, ValueError, KeyError):
            channel = None
        if channel == 'manual':
            status.set(f'현재 {current} · 설치 파일로 업데이트')
        else:
            check_for_setup(root, folder, current, status)


def check_for_setup(root, folder, current, status):
    from PySide6 import QtNetwork as N
    from app import center_window
    from ui_theme import dark_titlebar

    dialog = tk.Toplevel(root)
    dialog.title('업데이트 확인')
    dialog.transient(root)
    center_window(dialog, 480, 175)
    dark_titlebar(dialog)
    body = tk.ttk.Frame(dialog, padding=16)
    body.pack(fill='both', expand=True)
    notice = tk.StringVar(value='최신 버전을 확인하고 있습니다…')
    status.set(f'현재 {current} · 최신 버전 확인 중…')
    tk.ttk.Label(body, textvariable=notice).pack(fill='x')
    progress = tk.ttk.Progressbar(body)
    buttons = tk.ttk.Frame(body)
    buttons.pack(fill='x')
    update = tk.ttk.Button(buttons, text='업데이트 하기', state='disabled')
    update.pack(side='right')
    later = tk.ttk.Button(buttons, text='닫기', command=dialog.destroy)
    later.pack(side='right', padx=(0, 8))
    dialog.grab_set()

    network = N.QNetworkAccessManager(dialog._q)
    active = None
    output = None

    def cleanup(*_):
        nonlocal active, output
        reply, active = active, None
        if reply is not None:
            reply.abort()
        if output is not None:
            output.cancelWriting()
            output = None

    def dismiss(_):
        cancelled = active is not None
        cleanup()
        if cancelled:
            status.set(f'현재 {current} · 업데이트 취소됨')
    dialog.bind('<Destroy>', dismiss, add='+')

    def failed(error, retry):
        cleanup()
        progress.pack_forget()
        notice.set(str(error))
        status.set(f'현재 {current} · 업데이트 미완료')
        update.configure(text='다시 시도', state='normal', command=retry)
        later.configure(text='닫기')

    def request(url, consume, complete, retry):
        nonlocal active
        req = N.QNetworkRequest(tk.C.QUrl(url))
        req.setRawHeader(b'User-Agent', b'WorkSpace-Updater')
        req.setTransferTimeout(30000)
        req.setAttribute(N.QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         N.QNetworkRequest.RedirectPolicy.UserVerifiedRedirectPolicy)
        reply = network.get(req)
        active = reply
        reply.setReadBufferSize(1024 * 1024)

        def redirect(new_url):
            if active is not reply:
                return
            if new_url.scheme() == 'https' and new_url.host() in GITHUB_HOSTS:
                reply.redirectAllowed.emit()
            else:
                failed('지원하지 않는 다운로드 주소입니다.', retry)

        def read():
            if active is reply:
                try:
                    consume(bytes(reply.readAll()))
                except (OSError, ValueError) as error:
                    failed(error, retry)

        def finished():
            nonlocal active
            reply.deleteLater()
            if active is not reply:
                return
            if reply.error() != N.QNetworkReply.NetworkError.NoError:
                failed(reply.errorString(), retry)
                return
            read()
            if active is not reply:
                return
            active = None
            try:
                complete()
            except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
                failed(error, retry)

        reply.redirected.connect(redirect)
        reply.readyRead.connect(read)
        reply.finished.connect(finished)
        return reply

    def read_small(url, limit, done, retry):
        data = bytearray()
        def collect(block):
            if len(data) + len(block) > limit:
                raise UpdateError('업데이트 정보가 너무 큽니다.')
            data.extend(block)
        request(url, collect, lambda: done(bytes(data)), retry)

    def install(target):
        # NSIS requires the unquoted installation directory as the final argument.
        command = subprocess.list2cmdline([str(target), '/AUTORESTART=1', f'/WAITPID={os.getpid()}'])
        try:
            subprocess.Popen(command + ' /D=' + str(folder), executable=str(target), cwd=folder)
        except OSError as error:
            failed(error, lambda: install(target))
            return
        status.set('Setup 시작 · Work Space 종료 중')
        root.destroy()

    def download(setup):
        nonlocal output
        version, url = setup
        filename = url.rsplit('/', 1)[-1]
        update.configure(state='disabled')
        later.configure(text='취소')
        notice.set(f'{filename} 다운로드 중…')
        status.set(f'새 버전 {version} · 설치 파일 다운로드 중')
        progress.pack(fill='x', pady=10, before=buttons)
        progress.start()
        target = folder / 'downloads' / filename
        retry = lambda: download(setup)
        try:
            target.parent.mkdir(exist_ok=True)
            output = tk.C.QSaveFile(str(target))
            if not output.open(tk.C.QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(output.errorString())
        except OSError as error:
            failed(error, retry)
            return
        digest = hashlib.sha256()
        received = 0

        def write(block):
            nonlocal received
            received += len(block)
            if received > MAX_ARCHIVE:
                raise UpdateError('설치 파일 크기 제한을 초과했습니다.')
            if output.write(block) != len(block):
                raise OSError(output.errorString())
            digest.update(block)

        def verify(data):
            nonlocal output
            fields = data.decode('ascii').split()
            if (len(fields) != 2 or fields[1] != filename or not re.fullmatch('[0-9a-f]{64}', fields[0])
                    or not received or digest.hexdigest() != fields[0]):
                raise UpdateError('설치 파일 검증에 실패했습니다. 다시 다운로드해 주세요.')
            if not output.commit():
                raise OSError(output.errorString())
            output = None
            progress.stop()
            install(target)

        def downloaded():
            notice.set('다운로드 완료 · 설치 파일 확인 중…')
            read_small(url + '.sha256', 512, verify, retry)

        reply = request(url, write, downloaded, retry)
        def show_progress(count, total):
            if active is not reply:
                return
            if total > 0:
                progress._q.setRange(0, 100)
                progress._q.setValue(min(100, count * 100 // total))
            notice.set(f'{filename} · {count / (1024**2):,.1f} MB 받음')
        reply.downloadProgress.connect(show_progress)

    def checked(data):
        setup = latest_setup(current, json.loads(data))
        progress.pack_forget()
        if setup:
            notice.set(f'현재 {current} · 새 버전 {setup[0]}')
            status.set(f'새 버전 {setup[0]} · 업데이트 가능')
            update.configure(text='업데이트 하기', state='normal', command=lambda: download(setup))
            later.configure(text='나중에')
        else:
            notice.set('현재 최신 버전을 사용하고 있습니다.')
            status.set(f'현재 {current} · 최신 버전입니다.')
            dialog.after(500, dialog.destroy)

    def check():
        update.configure(state='disabled')
        notice.set('최신 버전을 확인하고 있습니다…')
        progress.pack(fill='x', pady=10, before=buttons)
        progress.start()
        read_small(SETUP_API + '/releases?per_page=30', 2 * 1024 * 1024, checked, check)

    check()
