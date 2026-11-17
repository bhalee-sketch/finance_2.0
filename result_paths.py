"""모든 업무 결과 Excel의 공통 저장 위치와 충돌 없는 이름."""
import os
import re
import threading
from datetime import datetime,timedelta
from pathlib import Path

_lock=threading.Lock()
_last=None


def desktop_dir():
    if os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                return Path(os.path.expandvars(winreg.QueryValueEx(key,'Desktop')[0]))
        except OSError:pass
    return Path.home()/'Desktop'


def results_dir():
    folder=desktop_dir()/'검증결과'
    folder.mkdir(parents=True,exist_ok=True)
    return folder


def result_path(feature):
    global _last
    label=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(feature)).strip(' .')
    if not label:raise ValueError('결과 파일의 기능 이름이 필요합니다.')
    folder=results_dir()
    with _lock:
        stamp=datetime.now()
        if _last is not None and stamp<=_last:stamp=_last+timedelta(microseconds=1)
        while True:
            path=folder/f'{label}_{stamp:%Y%m%d_%H%M%S_%f}.xlsx'
            if not path.exists():break
            stamp+=timedelta(microseconds=1)
        _last=stamp
    return path
