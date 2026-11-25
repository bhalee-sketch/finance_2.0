from hashlib import sha256
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time
from unittest.mock import patch

import pytest

from release_update import latest_setup


def release(version, *, prerelease=False, draft=False, checksum=True, state='uploaded'):
    filename = f'WorkSpace-Setup-{version}-x64.exe'
    assets = [{'name': filename, 'state': state}]
    if checksum:
        assets.append({'name': filename + '.sha256', 'state': 'uploaded'})
    return {'tag_name': 'v' + version, 'draft': draft, 'prerelease': prerelease, 'assets': assets}


def test_latest_setup_selects_newest_complete_stable_release():
    releases = [
        release('3.4.0', prerelease=True), release('3.3.9', draft=True),
        release('3.3.8', checksum=False), release('3.3.7', state='new'),
        release('3.3.5'), release('3.3.6'), release('3.3.3'),
    ]
    assert latest_setup('3.3.4', releases) == (
        '3.3.6',
        'https://github.com/bhalee-sketch/finance_2.0/releases/download/v3.3.6/WorkSpace-Setup-3.3.6-x64.exe',
    )


def test_latest_setup_ignores_installed_and_older_releases():
    assert latest_setup('3.3.4', [release('3.3.4'), release('3.3.3')]) is None


def test_patch_selection_requires_a_matching_pair_on_the_newest_release():
    item = release('3.4.7')
    name = 'WorkSpace-Patch-3.4.6-to-3.4.7-x64.exe'
    item['assets'].append({'name': name, 'state': 'uploaded'})
    assert '/WorkSpace-Setup-' in latest_setup('3.4.6', [item])[1]
    item['assets'].append({'name': name + '.sha256', 'state': 'uploaded'})
    assert latest_setup('3.4.6', [item])[1].endswith(name)
    assert '/WorkSpace-Setup-' in latest_setup('3.4.5', [item])[1]
    assert latest_setup('3.4.6', [item, release('3.4.8')])[0] == '3.4.8'


@pytest.mark.parametrize('action', ['skip', 'install', 'patch', 'full', 'bad_hash', 'cancel', 'launch_error'])
def test_foreground_setup_handoff(tmp_path, action):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6 import QtNetwork
    import qt_ui as tk
    from startup_update import check_for_setup

    patch_name = 'WorkSpace-Patch-3.4.4-to-3.4.5-x64.exe'
    filename = patch_name if action == 'patch' else 'WorkSpace-Setup-3.4.5-x64.exe'
    payload = b'MZ' + b'x' * 65536
    checksum = sha256(b'wrong' if action == 'bad_hash' else payload).hexdigest()
    paths = []
    paused = threading.Event()

    class Server(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            if self.path.startswith('/repos/'):
                item = release('3.4.5')
                if action in ('patch', 'full'):
                    item['assets'].extend({'name': n, 'state': 'uploaded'} for n in (patch_name, patch_name+'.sha256'))
                content = json.dumps([item]).encode()
            elif self.path.endswith('.sha256'):
                content = f'{checksum}  {filename}'.encode()
            else:
                assert self.path.endswith(filename)
                content = payload
            self.send_response(200)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            if content is payload and action == 'cancel':
                self.wfile.write(content[:1])
                paused.wait(5)
                return
            self.wfile.write(content)
        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(('127.0.0.1', 0), Server) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        class LocalNetwork(QtNetwork.QNetworkAccessManager):
            def get(self, request):
                url = request.url()
                url.setScheme('http')
                url.setHost('127.0.0.1')
                url.setPort(server.server_port)
                request.setUrl(url)
                return super().get(request)

        def wait(until):
            deadline = time.monotonic() + 5
            while not until() and time.monotonic() < deadline:
                tk.application().processEvents()
                time.sleep(.01)
            assert until()

        root = tk.Tk()
        root.geometry('600x400+40+55')
        try:
            with patch.object(QtNetwork, 'QNetworkAccessManager', LocalNetwork), patch('startup_update.subprocess.Popen') as launch:
                status = tk.StringVar()
                check_for_setup(root, tmp_path, '3.4.4', status)
                dialog = root.grab_current()
                assert dialog.title() == '업데이트 확인'
                from launcher import Launcher
                from types import SimpleNamespace
                root.protocol('WM_DELETE_WINDOW', lambda: Launcher.close(SimpleNamespace(root=root)))
                buttons = dialog._q.findChildren(tk.W.QPushButton)
                update = next(b for b in buttons if b.text() == '업데이트 하기')
                initial_frame = dialog._q.frameGeometry()
                wait(update.isEnabled)
                if action in ('patch', 'install'):
                    tk.application().processEvents()
                    frame = dialog._q.frameGeometry()
                    assert frame == initial_frame
                    owner_center = root._q.mapToGlobal(root._q.rect().center())
                    assert (frame.center() - owner_center).manhattanLength() <= 2
                    visible = [b for b in buttons if b.isVisible()]
                    assert len(visible) == (3 if action == 'patch' else 2)
                    left = min(b.geometry().left() for b in visible)
                    right = max(b.geometry().right() for b in visible)
                    message = dialog._q.findChild(tk.W.QLabel)
                    contents = message.parentWidget().rect()
                    assert message.alignment() == tk.C.Qt.AlignmentFlag.AlignCenter
                    assert abs(left - (contents.right() - right)) <= 2
                    bottom = max(b.geometry().bottom() for b in visible)
                    assert abs(message.y() - (contents.bottom() - bottom)) <= 2
                assert len(paths) == 1
                assert not (tmp_path / 'downloads').exists()
                if action == 'skip':
                    next(b for b in buttons if b.text() == '나중에').click()
                    assert not dialog.winfo_exists()
                    launch.assert_not_called()
                    return
                if action == 'launch_error':
                    launch.side_effect = OSError('launch failed')
                if action == 'full':
                    next(b for b in buttons if b.text() == '전체 설치본 받기').click()
                else:
                    update.click()
                wait(lambda: len(paths) >= 2)
                assert paths[1].endswith('/' + filename)
                if action == 'cancel':
                    assert dialog._q.frameGeometry() == initial_frame
                    assert dialog._q.findChild(tk.W.QProgressBar).isVisible()
                    next(b for b in buttons if b.text() == '취소').click()
                    paused.set()
                    assert root.winfo_exists()
                    assert not list((tmp_path / 'downloads').iterdir())
                    launch.assert_not_called()
                    return
                if action in ('bad_hash', 'launch_error'):
                    wait(lambda: update.isEnabled() and update.text() == '다시 시도')
                    assert root.winfo_exists()
                    if action == 'bad_hash':
                        assert not list((tmp_path / 'downloads').iterdir())
                        launch.assert_not_called()
                        return
                    launch.side_effect = None
                    tk.C.QTimer.singleShot(0, update.click)
                watchdog = tk.C.QTimer()
                watchdog.setSingleShot(True)
                watchdog.timeout.connect(lambda: tk.application().exit(1))
                watchdog.start(5000)
                try:
                    assert root.mainloop() == 0
                finally:
                    watchdog.stop()
                assert not root.winfo_exists()
                assert paths[2].endswith(filename + '.sha256')
                target = tmp_path / 'downloads' / filename
                assert target.read_bytes() == payload
                assert launch.call_args.kwargs['executable'] == str(target)
                assert f'/AUTORESTART=1 /WAITPID={os.getpid()} /D={tmp_path}' in launch.call_args.args[0]
        finally:
            paused.set()
            if root.winfo_exists():
                root.destroy()
            server.shutdown()
