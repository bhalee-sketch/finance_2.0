"""실행 중인 학사정보시스템의 화면 인식 진단. 사용자 입력/업무 데이터는 저장하지 않는다."""
import json
import os
import subprocess
from pathlib import Path

LABELS=['매입','매출','세금계산서','계산서','조회','작성년월일','합계표','기본엑셀','파일 이름','저장']


def inspect_school(use_foreground=False):
    if os.name!='nt':raise ValueError('학사 화면 인식 확인은 Windows PC에서 실행하세요.')
    script=Path(__file__).parent/'scripts'/'inspect_school.ps1'
    powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
    args=[str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-InspectorProcessId',str(os.getpid())]
    if use_foreground:args.append('-UseForeground')
    try:
        run=subprocess.run(args,
                           capture_output=True,encoding='utf-8-sig',errors='replace',timeout=35,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:return {'status':'error','stage':'화면 요소 읽기','error_type':'Timeout','message':'화면 인식이 35초 안에 완료되지 않았습니다. 학사 창의 응답 상태를 확인하세요.'}
    except OSError:return {'status':'error','stage':'PowerShell 시작','error_type':'LaunchFailure','message':'Windows 진단 프로세스를 시작하지 못했습니다.'}
    return decode_probe(run.stdout,run.returncode)


def decode_probe(stdout,returncode):
    try:
        report=json.loads(stdout)
        if not isinstance(report,dict) or report.get('status') not in ('ok','not_found','error'):raise ValueError()
        if returncode and report.get('status')=='ok':raise ValueError()
        return report
    except (ValueError,TypeError):
        return {'status':'error','exit_code':returncode,
                'message':'화면 인식을 완료하지 못했습니다. 실행 오류 진단을 저장했습니다.',
                'stage':'PowerShell 실행 또는 결과 읽기','error_type':'ProcessFailure' if returncode else 'InvalidResponse'}


def summary(report):
    rows=[]
    for label in LABELS:
        matches=[m for m in report.get('matches',[]) if m['label']==label and m['visible']]
        uia=[m for m in matches if m['backend']=='UIA']
        supported=sorted({p for m in uia for p in m.get('patterns',[])})
        status='UIA 인식' if uia else 'Win32 문자 인식' if matches else '미인식'
        rows.append((label,status,', '.join(supported) or ('추가 제어 확인 필요' if matches else '해당 화면을 열고 다시 확인')))
    types=report.get('control_types',{})
    grids=sum(types.get(t,0) for t in ('ControlType.DataGrid','ControlType.Table'))
    rows.append(('표',f'{grids}개 후보' if grids else '미인식','상단 합계 표인지 추가 확인 필요 · 표의 데이터는 읽지 않음'))
    edits=types.get('ControlType.Edit',0)
    rows.append(('입력칸',f'{edits}개 후보','날짜·파일명 입력칸 구분은 추가 확인 필요 · 입력값은 읽지 않음'))
    return rows


def save_report(report,stage):
    from result_paths import result_path
    path=result_path('학사 화면 인식 확인').with_suffix('.json')
    path.write_text(json.dumps({'screen':stage,**report},ensure_ascii=False,indent=2),encoding='utf-8')
    return path


def open_inspection(parent,center):
    import queue
    import threading
    import qt_ui as tk
    from qt_ui import ttk
    from ui_theme import dark_titlebar
    from statement_ui import table
    window=tk.Toplevel(parent);window.title('학사 화면 인식 확인 · 읽기 전용');dark_titlebar(window);center(window,850,610)
    body=ttk.Frame(window,padding=18);body.pack(fill='both',expand=True)
    ttk.Label(body,text='학사정보시스템 화면 인식 확인',style='Section.TLabel').pack(anchor='w')
    ttk.Label(body,text='학사 프로그램을 실행하거나 클릭·입력하지 않습니다.\n확인을 누른 후 5초 안에 학사 합계표, 우클릭 메뉴 또는 저장창을 직접 열어 두세요.\n표의 거래 내역·비밀번호·입력값·스크린샷은 진단에 저장하지 않습니다.',wraplength=800).pack(anchor='w',pady=12)
    use_foreground=tk.BooleanVar(value=False)
    ttk.Checkbutton(body,text='실행 파일 경로 대신 현재 활성 창 검사 (5초 안에 학사 창을 클릭하세요)',variable=use_foreground).pack(anchor='w',pady=(0,8))
    stage=tk.StringVar(value='합계표');bar=ttk.Frame(body);bar.pack(fill='x')
    ttk.Combobox(bar,textvariable=stage,values=['합계표','우클릭 메뉴','저장창'],state='readonly',width=15).pack(side='left')
    tree=table(body,['항목','인식 결과','설명'],auto_scroll=True)
    tree.column('항목',width=110);tree.column('인식 결과',width=150);tree.column('설명',width=490)
    status=tk.StringVar(value='이 검사는 인식 가능성 확인입니다. 자동 클릭·다운로드 성공을 의미하지 않습니다.')
    ttk.Label(body,textvariable=status,wraplength=800).pack(fill='x',pady=12)
    messages=queue.Queue();busy=False
    def poll():
        nonlocal busy
        if not window.winfo_exists():return
        try:ok,result=messages.get_nowait()
        except queue.Empty:window.after(100,poll);return
        busy=False;button.configure(state='normal')
        if not ok:status.set(result);return
        report,path=result
        tree.delete(*tree.get_children())
        for row in summary(report):tree.insert('','end',values=row)
        status.set((report.get('message') or (' / '.join(report.get('process_names',[]))+' · ')+f"창 {report.get('window_count',0)}개 · 요소 {report.get('scanned',0)}개 확인" )+(' · 일부만 조사됨' if report.get('truncated') else '')+f'\n진단 저장: {path}')
    def begin():
        nonlocal busy
        if busy:return
        busy=True;button.configure(state='disabled');selected=stage.get();foreground=use_foreground.get()
        def countdown(seconds):
            if not window.winfo_exists():return
            if seconds:
                status.set(f'{seconds}초 후 읽기 시작 · 학사 프로그램의 {selected} 화면을 직접 열어 두세요.')
                window.after(1000,lambda:countdown(seconds-1));return
            status.set('화면 요소를 읽고 있습니다… (최대 35초)')
            def work():
                try:
                    report=inspect_school(foreground);path=save_report(report,selected);messages.put((True,(report,path)))
                except Exception as exc:messages.put((False,str(exc) if isinstance(exc,ValueError) else '진단 저장 또는 실행에 실패했습니다.'))
            threading.Thread(target=work,daemon=True).start();poll()
        countdown(5)
    button=ttk.Button(bar,text='5초 후 인식 확인',command=begin);button.pack(side='left',padx=10)
