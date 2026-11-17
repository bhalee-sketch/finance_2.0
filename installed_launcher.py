"""Stable launcher: activate a prepared version and recover on startup failure."""
import ctypes
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from release_update import atomic_json,current_state,release_metadata,release_path,UpdateError

_LOCKS=[]

def instance_name(root,kind):
    return 'Local\\WorkSpace-'+kind+'-'+hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:24]

def instance_running(root,kind='application'):
    if sys.platform!='win32':return False
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenMutexW.argtypes=[ctypes.c_ulong,ctypes.c_bool,ctypes.c_wchar_p];api.OpenMutexW.restype=ctypes.c_void_p
    handle=api.OpenMutexW(0x100000,False,instance_name(root,kind))
    if not handle:return ctypes.get_last_error()==5
    api.CloseHandle.argtypes=[ctypes.c_void_p];api.CloseHandle(handle)
    return True

def single_instance(root,kind):
    if sys.platform!='win32':return True
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];api.CreateMutexW.restype=ctypes.c_void_p
    name=instance_name(root,kind)
    handle=api.CreateMutexW(None,False,name)
    if not handle:raise OSError('프로그램 실행 잠금을 만들지 못했습니다.')
    duplicate=ctypes.get_last_error()==183
    if duplicate:
        api.CloseHandle.argtypes=[ctypes.c_void_p];api.CloseHandle(handle);return False
    _LOCKS.append(handle)
    if kind=='application':_LOCKS.append(api.CreateMutexW(None,False,'Local\\WorkSpaceRunning'))
    return True

def wait_for_exit(pid,seconds=60):
    if not pid:return
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_bool,ctypes.c_ulong];api.OpenProcess.restype=ctypes.c_void_p
    api.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    api.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=api.OpenProcess(0x100000,False,int(pid))
    if not handle:
        if ctypes.get_last_error()==87:return
        raise UpdateError('현재 프로그램 종료 여부를 확인하지 못했습니다. 프로그램을 닫은 뒤 다시 실행하세요.')
    try:
        if api.WaitForSingleObject(handle,seconds*1000)!=0:raise UpdateError('현재 프로그램이 아직 실행 중입니다. 업데이트를 적용하지 않았습니다.')
    finally:api.CloseHandle(handle)

def start_version(root,version,timeout=45):
    folder=release_path(root,version);release_metadata(folder)
    marker=Path(root)/'runtime'/(uuid.uuid4().hex+'.ready');marker.parent.mkdir(exist_ok=True)
    env=dict(os.environ,WORKSPACE_INSTALL_ROOT=str(root),WORKSPACE_READY_FILE=str(marker),PYINSTALLER_RESET_ENVIRONMENT='1')
    process=subprocess.Popen([str(folder/'WorkSpaceApp.exe')],cwd=folder,env=env)
    try:
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if marker.exists() and marker.read_text(encoding='utf-8')==version and process.poll() is None:return True
            if process.poll() is not None:return False
            time.sleep(.1)
        # Do not terminate a slow app or launch a second copy. Let the user close it.
        raise UpdateError('프로그램 시작 확인이 지연되고 있습니다. 열려 있는 창을 확인하세요. 현재 버전 선택은 유지됩니다.')
    finally:marker.unlink(missing_ok=True)

def activate(root,version,start=start_version):
    root=Path(root);state=current_state(root);info=release_metadata(release_path(root,version))
    if info['version']!=version:raise UpdateError('버전 폴더가 올바르지 않습니다.')
    if state['current']==version:return start(root,version)
    # The old pointer remains authoritative until the new UI has actually opened.
    atomic_json(root/'pending.json',{'candidate':version,'current':state['current']})
    try:ready=start(root,version)
    except OSError:ready=False
    except Exception:
        (root/'pending.json').unlink(missing_ok=True);raise
    if ready:
        atomic_json(root/'current.json',{'current':version,'previous':state['current']})
        (root/'pending.json').unlink(missing_ok=True);return True
    (root/'pending.json').unlink(missing_ok=True)
    try:restored=start(root,state['current'])
    except OSError:restored=False
    if not restored:raise UpdateError('새 버전과 이전 버전 모두 실행하지 못했습니다. 기존 파일은 보존했습니다. 설치 폴더의 logs/app.log를 확인하세요.')
    raise UpdateError('새 버전이 실행되지 않아 이전 버전으로 복구했습니다.')

def main():
    from taskbar_identity import set_taskbar_identity
    set_taskbar_identity()
    import qt_ui as tk
    from qt_ui import messagebox
    root=Path(sys.executable).resolve().parent
    dialog=tk.Tk();dialog.withdraw()
    try:
        if not single_instance(root,'launcher'):
            messagebox.showinfo('Work Space','이미 실행 중이거나 업데이트를 준비 중입니다. 기존 창을 확인하세요.',parent=dialog);return
        if len(sys.argv)>1 and sys.argv[1] in ('--activate','--rollback'):
            if len(sys.argv)!=4:raise UpdateError('업데이트 실행 인자가 올바르지 않습니다.')
            wait_for_exit(int(sys.argv[3]));activate(root,sys.argv[2])
        else:
            if instance_running(root):
                messagebox.showinfo('Work Space','이미 실행 중입니다. 기존 메뉴 창 또는 플로팅을 확인하세요.',parent=dialog);return
            state=current_state(root)
            if not start_version(root,state['current']):
                previous=state.get('previous')
                if previous and messagebox.askyesno('실행 복구','현재 버전을 실행하지 못했습니다. 이전 버전으로 복원할까요?',parent=dialog):activate(root,previous)
                else:raise UpdateError('프로그램 실행에 실패했습니다. 설치 폴더의 logs/app.log를 확인하세요.')
    except Exception as exc:messagebox.showerror('Work Space 실행 / 업데이트',str(exc),parent=dialog)
    finally:dialog.destroy()

if __name__=='__main__':main()
