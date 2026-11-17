"""Exercise screen actions against isolated empty data; never an all-data parity claim."""
import os
import sys
# Windows' offscreen plugin has no system font database. Use native Qt there.
if sys.platform != 'win32':
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,tempfile,time,traceback
from contextlib import ExitStack
from unittest.mock import patch
import qt_ui as q
import app


def walk(parent):
    for c in list(parent.children.values()):
        yield c
        yield from walk(c)


def audit():
    report=[];errors=[]
    with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
        desktop=Path(folder);messages=[]
        for name in ('showinfo','showerror','showwarning'):stack.enter_context(patch.object(q.messagebox,name,side_effect=lambda *a,**kw:messages.append(a)))
        stack.enter_context(patch.object(q.messagebox,'askyesno',return_value=False))
        for name in ('askopenfilename','askopenfilenames','asksaveasfilename','askdirectory'):stack.enter_context(patch.object(q.filedialog,name,return_value='' if name!='askopenfilenames' else ()))
        stack.enter_context(patch.object(app,'desktop',return_value=desktop));stack.enter_context(patch.object(app,'open_result_file'))
        stack.enter_context(patch('result_paths.desktop_dir',return_value=desktop));stack.enter_context(patch('startup_update.check_on_start'))
        with patch.object(q.Tk,'mainloop'):app.main()
        root=q._default_root;root.report_callback_exception=lambda t,v,tb:errors.append(''.join(traceback.format_exception(t,v,tb)))
        def pump():
            end=time.monotonic()+.18
            while time.monotonic()<end:q.application().processEvents();time.sleep(.002)
        for group,cards in root._launcher.groups:
            for title,command in cards:
                before=set(root.children);start=len(errors)
                try:command();pump()
                except Exception:errors.append(traceback.format_exc())
                windows=[w for k,w in root.children.items() if k not in before and isinstance(w,q.Toplevel)]
                actions=[w for window in windows for w in walk(window) if type(w._q) is q.W.QPushButton]
                for w in actions:
                    if not w.winfo_exists():continue
                    caption=w.cget('text');row={'screen':title,'action':caption,'scope':'empty input and cancelled file dialogs'}
                    if any(term in caption for term in ('로그인','4종 받기','5초 후','다운로드 및 적용','이전 버전 복원','업데이트 확인')):
                        row['result']='manual: external authentication/platform';report.append(row);continue
                    if not w._q.isEnabled():row['result']='disabled: requires loaded data';report.append(row);continue
                    count=len(errors);m=len(messages)
                    w.invoke();pump()
                    row['result']='callback error' if len(errors)>count else 'executed';row['messages']=[list(x) for x in messages[m:]];row['errors']=errors[count:];report.append(row)
                    # Close auxiliary forms without committing blank settings/data.
                    for top in windows:
                        for child in list(top.children.values()):
                            if isinstance(child,q.Toplevel):
                                callback=child.protocol('WM_DELETE_WINDOW')
                                if callback:callback()
                                if child.winfo_exists():child.destroy()
                for top in windows:
                    callback=top.protocol('WM_DELETE_WINDOW')
                    if callback:callback()
                    if top.winfo_exists():top.destroy()
                pump()
                if len(errors)>start:print(title,'ERROR',flush=True)
        root.destroy()
    return {'actions':report,'callback_errors':errors,'limits':'Only empty-input/error paths. Successful real-data workflows and all dynamic popup actions require separate checks.'}

if __name__=='__main__':
    result=audit();output=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/financetool-ui-audit.json');output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(f"{len(result['actions'])} actions; {len(result['callback_errors'])} callback errors; {output}");raise SystemExit(bool(result['callback_errors']))
