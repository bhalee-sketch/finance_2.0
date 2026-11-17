"""첫 실행 준비 화면. 설치가 필요할 때만 pip를 실행한다."""
from pathlib import Path
import os
import sys
import subprocess
import threading
import queue
if '--qt-ready' not in sys.argv:
    from prepare_environment import run as prepare_runtime
    raise SystemExit(prepare_runtime())

import qt_ui as tk
from qt_ui import ttk

BASE=Path(__file__).resolve().parent
os.chdir(BASE)
(BASE/'logs').mkdir(exist_ok=True)
LOG=BASE/'logs'/'setup.log'
CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)
messages=queue.Queue()
root=tk.Tk();root.title('업무 도구 시작')
from ui_theme import apply_theme
apply_theme(root)
root.resizable(False,False)
width,height=480,255
root.geometry(f'{width}x{height}+{max(0,(root.winfo_screenwidth()-width)//2)}+{max(0,(root.winfo_screenheight()-height)//2)}')
frame=ttk.Frame(root,padding=26);frame.pack(fill='both',expand=True)
ttk.Label(frame,text='업무 도구',style='Title.TLabel').pack(anchor='w')
status=tk.StringVar(value='실행 환경을 확인하고 있습니다…')
ttk.Label(frame,textvariable=status,wraplength=420).pack(anchor='w',pady=14)
progress=ttk.Progressbar(frame,mode='indeterminate');progress.pack(fill='x');progress.start(12)
ttk.Label(frame,text='처음 실행하거나 필수 구성요소가 바뀐 경우에만 설치합니다.',wraplength=420,style='Muted.TLabel').pack(anchor='w',pady=12)
actions=ttk.Frame(frame);actions.pack(fill='x')
running=True
root.protocol('WM_DELETE_WINDOW',lambda:None if running else root.destroy())
CHECK="""import sys,importlib.metadata as m
from pathlib import Path
for line in Path(sys.argv[1]).read_text().splitlines():
 if not line.strip() or line.lstrip().startswith('#'):continue
 name,version=line.strip().split('==')
 try: current=m.version(name)
 except m.PackageNotFoundError:sys.exit(1)
 if current!=version:sys.exit(1)
"""

def prepare():
    lock=None
    try:
        if os.name=='nt':
            import msvcrt
            lock=(BASE/'logs'/'startup.lock').open('a+b');lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('다른 시작 준비 작업이 진행 중입니다. 잠시 후 다시 실행하세요.')
        python=BASE/'.venv'/'Scripts'/'python.exe';pythonw=python.with_name('pythonw.exe')
        with LOG.open('w',encoding='utf-8') as log:
            def run(args):
                result=subprocess.run(args,cwd=BASE,stdout=log,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW)
                if result.returncode:raise RuntimeError('준비에 실패했습니다. 오류 기록에서 자세한 내용을 확인하세요.')
            if not python.exists():
                messages.put(('status','처음 실행을 위한 환경을 준비하고 있습니다…'))
                run([sys.executable,'-m','venv',str(BASE/'.venv')])
            ready=subprocess.run([str(python),'-c',CHECK,str(BASE/'requirements.txt')],stdout=log,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW).returncode==0
            if not ready:
                messages.put(('status','필수 구성요소를 설치하고 있습니다. 첫 설치에는 인터넷 연결이 필요합니다…'))
                run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(BASE/'requirements.txt')])
            messages.put(('status','준비 완료 · 프로그램을 여는 중…'))
            subprocess.Popen([str(pythonw),str(BASE/'bootstrap.pyw')],cwd=BASE,creationflags=CREATE_NO_WINDOW)
        messages.put(('done',None))
    except Exception as e:messages.put(('error',str(e)))
    finally:
        if lock is not None:lock.close()

def poll():
    global running
    try:
        while True:
            kind,value=messages.get_nowait()
            if kind=='status':status.set(value)
            elif kind=='done':root.destroy();return
            else:
                running=False;progress.stop();status.set(value)
                ttk.Button(actions,text='오류 기록 열기',command=lambda:os.startfile(LOG)).pack(side='left')
                ttk.Button(actions,text='닫기',command=root.destroy).pack(side='right');return
    except queue.Empty:root.after(80,poll)
threading.Thread(target=prepare,daemon=True).start();root.after(80,poll);root.mainloop()
