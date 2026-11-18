"""Source test launcher: reuse matching libraries, otherwise use an isolated cached venv."""
from pathlib import Path
from datetime import datetime
import hashlib
import importlib.metadata
import os
import subprocess
import sys

BASE=Path(__file__).resolve().parent
PROBE="""import importlib.metadata as m,sys
from pathlib import Path
for line in Path(sys.argv[1]).read_text().splitlines():
 if not line.strip() or line.lstrip().startswith('#'):continue
 name,version=line.strip().split('==')
 try:installed=m.version(name)
 except m.PackageNotFoundError:sys.exit(1)
 if installed!=version:sys.exit(1)
"""


def compatible(python):
    return subprocess.run([str(python),'-c',PROBE,str(BASE/'requirements.txt')],cwd=BASE).returncode==0


def runtime_path():
    identity=f'{sys.version_info.major}.{sys.version_info.minor}-'+hashlib.sha256((BASE/'requirements.txt').read_bytes()).hexdigest()[:16]
    home=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'WorkSpaceSource'/'runtimes'
    return home/identity


def prepare():
    if compatible(sys.executable):return Path(sys.executable)
    environment=runtime_path();python=environment/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    environment.parent.mkdir(parents=True,exist_ok=True)
    # Serialize setup across ZIP versions sharing the same cached environment.
    with environment.with_suffix('.lock').open('a+b') as lock:
        if os.name=='nt':
            import msvcrt
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Another source environment setup is running. Retry after it finishes.') from None
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX)
        if not python.exists():subprocess.run([sys.executable,'-m','venv',str(environment)],check=True)
        if not compatible(python):
            print('Installing required libraries in the isolated test environment...',flush=True)
            subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(BASE/'requirements.txt')],check=True)
            if not compatible(python):raise RuntimeError('Library verification failed.')
    return python


def run_source(python):
    path = BASE/'logs'/'process-exit.log'
    path.parent.mkdir(exist_ok=True)
    with path.open('a', encoding='utf-8', buffering=1) as log:
        log.write(f'\nProcess start {datetime.now().isoformat()}\n')
        result = subprocess.run([str(python), str(BASE/'source_start.py'), '--run'],
                                cwd=BASE, stderr=log, env=dict(os.environ, PYTHONFAULTHANDLER='1'))
        code = result.returncode
        log.write(f'Process exit {datetime.now().isoformat()} code={code} (0x{code & 0xffffffff:08X})\n')
    if code:
        print(f'Application exited with code {code} (0x{code & 0xffffffff:08X}). See {path}', file=sys.stderr)
    return code


def main():
    if sys.version_info<(3,12):raise RuntimeError('Python 3.12 or later is required.')
    if '--run' in sys.argv:
        import runpy
        from qt_ui import application
        from source_ui_diagnostics import GuiWatchdog
        watchdog=GuiWatchdog(application(),BASE/'logs'/'ui-freeze.log')
        try:runpy.run_path(str(BASE/'bootstrap.pyw'),run_name='__main__')
        finally:watchdog.close()
        return 0
    print('Checking Python and library versions. Existing EXE installations are not changed.',flush=True)
    python=prepare()
    print('Starting source test. Application log: '+str(BASE/'logs/app.log'),flush=True)
    return run_source(python)


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Source startup failed: '+str(exc),file=sys.stderr);raise SystemExit(1)
