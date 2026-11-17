"""Dependency bootstrap using only the standard library, before Qt is available."""
from pathlib import Path
import os
import subprocess
import sys


def run():
    base=Path(__file__).resolve().parent
    logs=base/'logs';logs.mkdir(exist_ok=True)
    python=base/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    lock=None
    try:
        if os.name=='nt':
            import msvcrt
            lock=(logs/'startup.lock').open('a+b');lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        with (logs/'setup.log').open('a',encoding='utf-8') as log:
            def checked(args):
                subprocess.run(args,cwd=base,stdout=log,stderr=subprocess.STDOUT,creationflags=flags,check=True)
            if not python.exists():checked([sys.executable,'-m','venv',str(base/'.venv')])
            probe="import importlib.metadata as m,sys; from pathlib import Path; specs=[s.strip().split('==') for s in Path(sys.argv[1]).read_text().splitlines() if s.strip() and not s.lstrip().startswith('#')]; sys.exit(0 if all(m.version(n)==v for n,v in specs) else 1)"
            result=subprocess.run([str(python),'-c',probe,str(base/'requirements.txt')],cwd=base,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
            if result.returncode:checked([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(base/'requirements.txt')])
        executable=python.with_name('pythonw.exe') if os.name=='nt' else python
        subprocess.Popen([str(executable),str(base/'startup.pyw'),'--qt-ready'],cwd=base,creationflags=flags)
        return 0
    except Exception:
        import traceback
        with (logs/'setup.log').open('a',encoding='utf-8') as log:traceback.print_exc(file=log)
        if os.name=='nt':
            # Last-resort OS error reporting when Qt cannot yet be imported.
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,f'실행 환경 준비에 실패했습니다.\n오류 기록: {logs / "setup.log"}','Work Space',0x10)
        return 1
    finally:
        if lock is not None:lock.close()
