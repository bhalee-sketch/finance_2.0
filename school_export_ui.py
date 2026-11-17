"""Start four school exports from the month selected on the tax verification screen."""
import queue
import threading
import qt_ui as tk
from qt_ui import ttk, messagebox
from school_export import KINDS, RUN_LOCK, ExportError, ExportRunner
from school_windows import WindowsSchool
from verifier import year_folder
from ui_theme import dark_titlebar


def open_school_export(parent, root_path, initial_year, initial_month, center):
    try:
        month = int(initial_month)
        if not 1 <= month <= 12:
            raise ValueError('월을 확인하세요.')
        destination = (year_folder(root_path, initial_year) / f'{month}월').resolve()
    except ValueError as exc:
        messagebox.showerror('학사 자료 저장', str(exc), parent=parent)
        return
    if not RUN_LOCK.acquire(blocking=False):
        messagebox.showinfo('학사 자료 저장', '이미 학사 자료를 저장하고 있습니다.', parent=parent)
        return
    window = tk.Toplevel(parent)
    window.title('학사 자료 저장'); dark_titlebar(window); center(window, 860, 400)
    body = ttk.Frame(window, padding=18); body.pack(fill='both', expand=True)
    ttk.Label(body, text=f'{initial_year}년 {month}월 · 학사 자료 4종 저장', style='Section.TLabel').pack(anchor='w')
    ttk.Label(body, text=f'저장 폴더: {destination}', wraplength=810).pack(anchor='w', pady=8)
    ttk.Label(body, text='학사 합계표를 활성화해 자동 저장합니다. 실행 중에는 마우스·키보드 사용을 멈추세요.\n조회 기간은 학사 화면에 설정된 기간을 사용합니다. Esc 또는 중단으로 멈출 수 있습니다.', wraplength=810).pack(anchor='w')
    tree = ttk.Treeview(body, columns=('kind','state','file'), show='headings', height=4)
    for key, title, width in [('kind','자료',145), ('state','상태',95), ('file','저장 파일 / 확인사항',550)]:
        tree.heading(key,text=title); tree.column(key,width=width)
    for kind in KINDS:
        tree.insert('', 'end', iid=kind, values=(kind,'대기',''))
    tree.pack(fill='both', expand=True, pady=10)
    status = tk.StringVar(value='학사 창을 찾고 있습니다…')
    ttk.Label(body, textvariable=status, wraplength=810).pack(anchor='w', pady=8)
    stop = threading.Event(); messages = queue.Queue(); busy = True; closing = False
    actions = ttk.Frame(body); actions.pack(fill='x')
    cancel = ttk.Button(actions, text='중단', command=stop.set); cancel.pack(side='left')
    def open_folder():
        import os
        try:
            destination.mkdir(parents=True, exist_ok=True); os.startfile(destination)
        except (OSError, AttributeError):
            status.set('월 폴더를 열지 못했습니다.')
    folder_button = ttk.Button(actions, text='월 폴더 열기', command=open_folder, state='disabled')
    folder_button.pack(side='right')
    def work():
        try:
            # Preflight existing files before bringing the application forward.
            for kind in KINDS:
                if list(destination.glob(f'학사{kind}.*')):
                    raise ExportError(f'학사{kind} 파일이 이미 있습니다. 기존 파일을 다른 폴더로 옮긴 후 실행하세요.')
            backend = WindowsSchool(); backend.activate_default(stop)
            runner = ExportRunner(backend, stop, lambda *args: messages.put(('progress', args)))
            saved = runner.run(destination, KINDS)
            messages.put(('done', len(saved)))
        except Exception as exc:
            messages.put(('error', str(exc) if isinstance(exc, ExportError) else '저장 또는 파일 검증에 실패했습니다. 학사 창과 월 폴더의 저장 결과를 확인하세요.'))
    def poll():
        nonlocal busy
        try:
            while True:
                kind, value = messages.get_nowait()
                if kind == 'progress':
                    label, state, detail = value; tree.item(label, values=value); status.set(f'{label}: {state}')
                    continue
                if kind == 'done':
                    status.set(f'{value}종 저장 완료.')
                    window.deiconify(); window.lift(); window.attributes('-topmost', True)
                    window.after(1000, lambda: window.winfo_exists() and window.attributes('-topmost', False))
                    window.focus_force()
                else:
                    status.set(value)
                    for label in KINDS:
                        vals = tree.item(label, 'values')
                        if vals[1] in ('조회 중','저장 중'):
                            tree.item(label, values=(label,'중단',value))
                busy = False; RUN_LOCK.release()
                cancel.configure(state='disabled'); folder_button.configure(state='normal')
                if closing:
                    window.destroy()
                return
        except queue.Empty:
            window.after(100, poll)
    def close():
        nonlocal closing
        if busy:
            closing = True; stop.set(); status.set('작업 중단 후 창을 닫습니다…')
        else:
            window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    def start():
        threading.Thread(target=work, daemon=True).start()
        poll()
    window.after(100, start)
