"""Qt UI와 Chrome 제어는 별도 스레드. 비밀번호는 저장하지 않고 로그인 한 번에만 사용한다."""
import queue
import json
from datetime import datetime
import threading
from pathlib import Path
import qt_ui as tk
from qt_ui import ttk,messagebox
from hometax_login import CertificateLogin,LoginError,OneTimePassword,OWNER,EXPIRY
from hometax_download import HOME,MENU,BrowserDownloader
from hometax_window import window_state,successful_downloads
from verifier import KINDS,year_folder
from ui_theme import dark_titlebar


def ask_certificate_password(parent):
    dialog=tk.Toplevel(parent,show_on_create=False);dialog.title('공동인증서 비밀번호');dark_titlebar(dialog)
    dialog.transient(parent)
    panel=ttk.Frame(dialog,padding=18);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text=f'지정 인증서 만료일: {EXPIRY}',style='Accent.TLabel').pack(anchor='w')
    ttk.Label(panel,text='인증서 비밀번호',wraplength=360).pack(anchor='w',pady=(10,4))
    entry=ttk.Entry(panel,show='●',width=28);entry.pack(fill='x',pady=6)
    ttk.Label(panel,text='비밀번호는 저장하지 않습니다.',style='Muted.TLabel').pack(anchor='w',pady=(4,0))
    result=[]
    def finish(submit=False):
        if submit:
            value=entry.get()
            if not value:return
            result.append(OneTimePassword(value));value=None
        entry.delete(0,'end');dialog.destroy()
    buttons=ttk.Frame(panel);buttons.pack(fill='x',pady=(12,0))
    ttk.Button(buttons,text='취소',command=finish).pack(side='right')
    ttk.Button(buttons,text='로그인 시작',command=lambda:finish(True)).pack(side='right',padx=8)
    dialog.bind('<Return>',lambda e:finish(True));dialog.bind('<Escape>',lambda e:finish())
    dialog.protocol('WM_DELETE_WINDOW',finish)
    dialog.update_idletasks()
    center=parent._q.mapToGlobal(parent._q.rect().center())
    screen=(tk.application().screenAt(center) or parent._q.screen()).availableGeometry()
    width=min(max(400,dialog.winfo_reqwidth()+12),screen.width()-24)
    height=min(max(220,dialog.winfo_reqheight()+12),screen.height()-24)
    x=max(screen.left()+12,min(center.x()-width//2,screen.right()-width-11))
    y=max(screen.top()+12,min(center.y()-height//2,screen.bottom()-height-11))
    dialog.geometry(f'{width}x{height}{x:+d}{y:+d}');dialog._q.setFixedSize(width,height)
    dialog.deiconify();dialog.grab_set();entry.focus_set()
    parent.wait_window(dialog)
    return result.pop() if result else None


def open_hometax(parent,root_path,initial_year,initial_month,center,open_file):
    window=tk.Toplevel(parent,show_on_create=False);window.title('홈택스 자료 내려받기');dark_titlebar(window)
    window.minsize(860,620);center(window,1000,720)
    body=ttk.Frame(window,padding=18);body.pack(fill='both',expand=True)
    ttk.Label(body,text='홈택스 자료 내려받기',style='Section.TLabel').pack(anchor='w')
    ttk.Label(body,text='로그인 후 자료 4종을 내려받습니다. 비밀번호는 저장하지 않습니다.\n자동 입력이 어려우면 Chrome에서 직접 로그인한 뒤 진행하세요.',wraplength=920).pack(fill='x',pady=8)
    ttk.Label(body,text=MENU,style='Muted.TLabel',wraplength=800).pack(anchor='w')
    ttk.Label(body,text=f'지정 인증서: 만료일 {EXPIRY} (소유자명 무관 · 일치하는 1개만 선택)',style='Accent.TLabel').pack(anchor='w',pady=(5,0))
    bar=ttk.Frame(body);bar.pack(fill='x',pady=12)
    year=tk.StringVar(value=str(initial_year));month=tk.StringVar(value=str(initial_month))
    ttk.Label(bar,text='연도').pack(side='left');year_input=ttk.Spinbox(bar,from_=1900,to=9999,textvariable=year,width=7);year_input.pack(side='left',padx=6)
    ttk.Label(bar,text='월').pack(side='left');month_input=ttk.Combobox(bar,textvariable=month,values=[str(m) for m in range(1,13)],state='readonly',width=5);month_input.pack(side='left',padx=6)
    target=tk.StringVar();ttk.Label(body,textvariable=target,style='Accent.TLabel',wraplength=800).pack(anchor='w')
    def preview(*args):
        try:target.set('저장 폴더: '+str(year_folder(root_path,year.get())/f'{int(month.get())}월'))
        except ValueError:target.set('연도와 월을 확인하세요.')
    year.trace_add('write',preview);month.trace_add('write',preview);preview()
    buttons=ttk.Frame(body);buttons.pack(fill='x',pady=12)
    tree=ttk.Treeview(body,columns=('kind','state','info'),show='headings',height=5)
    for key,label,width in [('kind','자료 종류',150),('state','진행',125),('info','저장 파일 / 확인사항',500)]:tree.heading(key,text=label);tree.column(key,width=width,anchor='w')
    tree.pack(fill='both',expand=True)
    for kind in KINDS:tree.insert('','end',iid=kind,values=(kind,'대기',''))
    status=tk.StringVar(value='실제 홈택스 화면에서의 첫 실행 확인이 필요합니다. 기존 자료는 덮어쓰지 않습니다.')
    ttk.Label(body,textvariable=status,wraplength=800,style='Muted.TLabel').pack(fill='x',pady=10)
    commands=queue.Queue();messages=queue.Queue();stop=threading.Event();worker=None;busy=False;ready=False;closing=False;auto_pending=False
    def send(kind,value=None):messages.put((kind,value))
    def clear_commands():
        removed=False
        while True:
            try:
                command,args=commands.get_nowait()
                if command=='login_download':args[2].clear()
                if command in ('login_download','download'):removed=True
            except queue.Empty:return removed
    def work(minimized=False):
        browser=None
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                try:browser=playwright.chromium.launch(channel='chrome',headless=False,args=['--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows'])
                except Exception:
                    send('error','Chrome을 열지 못했습니다. Chrome 설치 여부와 보안 프로그램을 확인하세요.');return
                context=browser.new_context(accept_downloads=True);page=context.new_page()
                downloader=BrowserDownloader(context,stop,lambda value:send('progress',value),minimized=minimized)
                def restore_windows():
                    for current_page in context.pages:window_state(context,current_page,'normal')
                try:page.goto(HOME,wait_until='domcontentloaded',timeout=60000)
                except Exception:send('progress','Chrome에서 홈택스 접속과 로그인을 직접 진행하세요.')
                send('ready')
                while browser.is_connected():
                    try:command,args=commands.get_nowait()
                    except queue.Empty:
                        if context.pages:
                            try:context.pages[0].wait_for_timeout(100)
                            except Exception:break
                        else:break
                        continue
                    if command=='close':break
                    if command=='login_download':
                        request_year,request_month,secret=args;args=None
                        downloader.minimized=True;window_state(context,page,'minimized')
                        login=CertificateLogin(downloader)
                        try:
                            login.run(secret)
                            downloader.check()
                            result=downloader.run(root_path,request_year,request_month);send('done',result)
                            if successful_downloads(result):break
                            restore_windows()
                        except LoginError as exc:
                            restore_windows()
                            diagnostic_path=None
                            try:
                                folder=year_folder(root_path,request_year)/'홈택스확인대기'
                                folder.mkdir(parents=True,exist_ok=True)
                                diagnostic_path=folder/f'로그인진단_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
                                diagnostic_path.write_text(json.dumps(login.diagnostic(),ensure_ascii=False,indent=2),encoding='utf-8')
                            except Exception:diagnostic_path=None
                            send('error',str(exc)+(f' / 진단: {diagnostic_path}' if diagnostic_path else ''))
                        except Exception:
                            restore_windows();send('error','로그인 또는 다운로드가 중단되었습니다. Chrome 화면을 확인하세요.')
                        finally:secret.clear();secret=None
                    if command=='download':
                        try:
                            downloader.minimized=True;window_state(context,page,'minimized')
                            result=downloader.run(root_path,*args);send('done',result)
                            if successful_downloads(result):break
                            restore_windows()
                        except Exception:
                            restore_windows();send('error','다운로드를 시작하지 못했습니다. 저장 폴더와 Chrome 화면을 확인하세요.')
                browser.close()
        except ImportError:send('error','필수 구성요소가 없습니다. 프로그램을 종료하고 실행 파일로 다시 시작해 설치를 완료하세요.')
        except Exception:send('error','Chrome 연결이 종료되었습니다. Chrome 열기로 다시 시작하세요.')
        finally:
            if browser:
                try:browser.close()
                except Exception:pass
            clear_commands();send('closed')
    def launch(minimized=False):
        nonlocal worker,busy
        clear_commands()
        stop.clear();busy=True;status.set('Chrome을 여는 중입니다…');update_buttons()
        worker=threading.Thread(target=work,args=(minimized,),daemon=True);worker.start()
    def download():
        nonlocal busy
        try:
            year_folder(root_path,year.get());args=(int(year.get()),int(month.get()))
            if not 1<=args[1]<=12:raise ValueError('월을 1~12 사이로 선택하세요.')
        except ValueError as e:messagebox.showerror('조회 조건',str(e),parent=window);return
        for kind in KINDS:tree.item(kind,values=(kind,'대기',''))
        stop.clear();busy=True;update_buttons();commands.put(('download',args));status.set('조회·다운로드 중입니다. 자동화 Chrome 창은 직접 조작하지 마세요.')
    def login_download():
        nonlocal busy,auto_pending
        if busy or closing:return
        try:
            year_folder(root_path,year.get());y,m=int(year.get()),int(month.get())
            if not 1<=m<=12:raise ValueError('월을 1~12 사이로 선택하세요.')
        except ValueError as exc:messagebox.showerror('조회 조건',str(exc),parent=window);return
        secret=ask_certificate_password(window)
        if secret is None:return
        try:
            auto_pending=True
            if not ready:launch(minimized=True)
            else:stop.clear()
            for kind in KINDS:tree.item(kind,values=(kind,'대기',''))
            busy=True;update_buttons();commands.put(('login_download',(y,m,secret)))
            status.set('공동인증서 로그인 후 4종 다운로드를 진행합니다. Chrome 창은 직접 조작하지 마세요.')
        except Exception:
            secret.clear();auto_pending=False;busy=False;update_buttons()
            status.set('로그인을 시작하지 못했습니다. 다시 시도해 주세요.')
    def cancel():
        nonlocal auto_pending,busy
        stop.set();removed=clear_commands();auto_pending=False
        if removed and ready:busy=False
        update_buttons();status.set('현재 단계가 끝나면 중단합니다. 이미 저장한 파일은 유지됩니다.')
    def update_buttons():
        if closing:
            for widget in (auto_button,launch_button,download_button,cancel_button,year_input,month_input):widget.configure(state='disabled')
            return
        auto_button.configure(state='disabled' if busy else 'normal')
        launch_button.configure(state='disabled' if busy or ready else 'normal');download_button.configure(state='normal' if ready and not busy else 'disabled')
        cancel_button.configure(state='normal' if busy else 'disabled')
        year_input.configure(state='disabled' if busy else 'normal');month_input.configure(state='disabled' if busy else 'readonly')
    auto_button=ttk.Button(buttons,text='로그인 · 4종 받기',command=login_download);auto_button.pack(side='left',padx=(0,7))
    launch_button=ttk.Button(buttons,text='Chrome 열기 · 직접 로그인',command=launch);launch_button.pack(side='left',padx=(0,7))
    download_button=ttk.Button(buttons,text='로그인 완료 · 4종 받기',command=download,state='disabled');download_button.pack(side='left',padx=7)
    cancel_button=ttk.Button(buttons,text='중단',command=cancel,state='disabled');cancel_button.pack(side='left',padx=7)
    def open_folder():
        try:
            folder=year_folder(root_path,year.get())/f'{int(month.get())}월';folder.mkdir(parents=True,exist_ok=True);open_file(folder)
        except Exception as e:messagebox.showerror('폴더 열기',str(e),parent=window)
    ttk.Button(buttons,text='월 폴더 열기',command=open_folder).pack(side='right')
    def close():
        nonlocal closing
        if worker and worker.is_alive():closing=True;stop.set();clear_commands();commands.put(('close',None));status.set('Chrome 연결을 정리하고 있습니다…');return
        window.destroy()
    def poll():
        nonlocal busy,ready,closing,auto_pending
        try:
            while True:
                kind,value=messages.get_nowait()
                if kind=='ready':
                    ready=True;busy=auto_pending
                    if not auto_pending:status.set('공동인증서 로그인과 사업자 선택을 완료한 뒤 4종 받기를 누르세요.')
                elif kind=='progress':status.set(value)
                elif kind=='done':
                    busy=False;auto_pending=False
                    for item in value:tree.item(item[0],values=item)
                    complete=sum(row[1] in ('저장 완료','기존 파일 유지') for row in value)
                    status.set(f'{complete}/4종 준비됨. 중단 항목은 Chrome 및 연도 폴더의 홈택스확인대기를 확인한 뒤 다시 시도하세요.' if complete<4 else '4종이 준비되어 자동화 Chrome을 종료했습니다. 세금계산서 검증을 실행할 수 있습니다.')
                elif kind=='error':busy=False;auto_pending=False;status.set(value)
                elif kind=='closed':
                    ready=False;busy=False;auto_pending=False
                    if closing:window.destroy();return
                update_buttons()
        except queue.Empty:pass
        if window.winfo_exists():window.after(100,poll)
    window.protocol('WM_DELETE_WINDOW',close);window.after(100,poll)
    window.deiconify()
