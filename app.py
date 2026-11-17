"""Windows/macOS 데스크톱 메뉴 프로그램."""
from pathlib import Path
from datetime import date
import os
import sys
import subprocess
import threading
import queue
import qt_ui as tk
from qt_ui import ttk, filedialog, messagebox
from verifier import PERIODS, run, year_folder, create_year_folders
from account_verifier import yesterday, dated_folder, create_input_folder, run_account, find_inputs
from ui_theme import apply_theme, dark_titlebar
from deposit_ui import open_deposit
from loan_ui import open_loans
from transfer_ui import open_transfer
from macro_ui import open_macro
from launcher import Launcher
from statement_ui import open_statement_view,open_statement_verify
from finance_ui import open_analysis,open_ledger,open_merge
from audit_ui import open_audit
from closing_review_ui import open_closing_review

def open_result_file(path):
    path = str(Path(path).resolve(strict=True))
    if sys.platform == 'win32':
        os.startfile(path)
    else:
        command = 'open' if sys.platform == 'darwin' else 'xdg-open'
        subprocess.run([command, path], check=True, capture_output=True, timeout=15)


from result_paths import desktop_dir as desktop

def center_window(window, width, height):
    window.update_idletasks()
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f'{width}x{height}+{x}+{y}')


def open_account(parent):
    window=tk.Toplevel(parent); window.title('예금시재 검증')
    center_window(window,780,740);dark_titlebar(window)
    frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
    path=tk.StringVar(value=str(desktop()/'settings'/'account verification'))
    day=tk.StringVar(value=yesterday())
    cms=tk.StringVar();school=tk.StringVar()
    ttk.Label(frame,text='예금시재 계좌별 검증',style='Section.TLabel').pack(anchor='w',pady=(0,16))
    ttk.Label(frame,text='기본 폴더 (account verification)').pack(anchor='w')
    ttk.Entry(frame,textvariable=path).pack(fill='x',pady=5)
    def browse_root():
        selected=filedialog.askdirectory(parent=window)
        if selected: path.set(selected)
    ttk.Button(frame,text='폴더 변경',command=browse_root).pack(anchor='e')
    row=ttk.Frame(frame);row.pack(fill='x',pady=12)
    ttk.Label(row,text='검증 날짜').pack(side='left',padx=(0,10))
    ttk.Entry(row,textvariable=day,width=16).pack(side='left')
    def create_folder():
        try:
            folder=create_input_folder(path.get(),day.get())
            status.set(f'폴더 준비 완료: {folder}')
            open_result_file(folder)
        except (ValueError,OSError,subprocess.SubprocessError) as e:
            messagebox.showwarning('폴더 확인',str(e),parent=window)
    ttk.Button(row,text='검증파일 폴더 만들기',command=create_folder).pack(side='right')
    ttk.Label(frame,text='기본 날짜는 어제입니다. 날짜 폴더에 CMS·학사 자료를 넣어 주세요.\n예: 2026-11-01/CMS계좌현황.xlsx, 학사계좌현황.xls',wraplength=660).pack(anchor='w',pady=10)
    ttk.Label(frame,text='파일명으로 자동 검색합니다. 필요하면 아래에서 직접 선택하세요.').pack(anchor='w')
    def select_file(variable):
        try: initial=dated_folder(path.get(),day.get())
        except ValueError: initial=Path(path.get())
        selected=filedialog.askopenfilename(parent=window,initialdir=str(initial),filetypes=[('Excel','*.xls *.xlsx *.xlsm')])
        if selected:variable.set(selected)
    for label,variable in [('CMS 파일',cms),('학사 파일',school)]:
        line=ttk.Frame(frame);line.pack(fill='x',pady=8)
        ttk.Label(line,text=label,width=10).pack(side='left')
        ttk.Entry(line,textvariable=variable).pack(side='left',fill='x',expand=True)
        ttk.Button(line,text='선택',command=lambda v=variable:select_file(v)).pack(side='right')
    def reset_files(*_):
        cms.set('');school.set('')
    day.trace_add('write',reset_files);path.trace_add('write',reset_files)
    def search_files():
        reset_files()
        try:
            folder=dated_folder(path.get(),day.get())
            cms_file,school_file=find_inputs(folder)
            cms.set(str(cms_file));school.set(str(school_file))
            status.set('폴더 검색 완료 · CMS와 학사 파일을 찾았습니다.')
        except (ValueError,OSError) as e:
            status.set('파일 검색 확인 필요')
            messagebox.showwarning('파일 검색 결과',str(e),parent=window)
    ttk.Button(frame,text='날짜 폴더에서 파일 찾기',command=search_files).pack(anchor='e')
    status=tk.StringVar(value='검증 완료 후 결과를 저장하고 자동으로 엽니다.')
    window._work_status=status
    ttk.Label(frame,textvariable=status,wraplength=660,style='Muted.TLabel').pack(anchor='w',pady=16)
    messages=queue.Queue();busy=False
    def close():
        if not busy:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    def poll():
        nonlocal busy
        try:success,result=messages.get_nowait()
        except queue.Empty:window.after(100,poll);return
        busy=False;button.configure(state='normal')
        if success:
            status.set(f'저장 완료: {result}')
            try:open_result_file(result)
            except (OSError,subprocess.SubprocessError) as e:
                messagebox.showwarning('저장 완료 · 자동 열기 실패',f'{result}\n\n{e}',parent=window)
        else:
            status.set('자료 확인 필요');messagebox.showerror('검증 중단',result,parent=window)
    def execute():
        nonlocal busy
        args=(path.get(),day.get(),cms.get() or None,school.get() or None)
        busy=True;button.configure(state='disabled');status.set('계좌별 잔액을 검증하고 있습니다…')
        def work():
            try:messages.put((True,str(run_account(*args))))
            except Exception as e:messages.put((False,str(e)))
        threading.Thread(target=work,daemon=True).start();window.after(100,poll)
    button=ttk.Button(frame,text='예금시재 검증 실행  →',command=execute,style='Primary.TButton');button.pack(fill='x',pady=10)


def main():
    root=tk.Tk()
    from app_icon import apply_app_icon
    apply_app_icon(root)
    from app_version import application_title
    root.title(application_title()); apply_theme(root)
    def open_tax():
        window=tk.Toplevel(root); window.title('세금계산서 검증'); center_window(window,760,760); dark_titlebar(window)
        frame=ttk.Frame(window,padding=24); frame.pack(fill='both',expand=True)
        path=tk.StringVar(value=str(desktop()/'settings'/'taxinvoice'))
        ttk.Label(frame,text='세금계산서 검증',style='Section.TLabel').pack(anchor='w')
        ttk.Entry(frame,textvariable=path).pack(fill='x',pady=10)
        def open_month_folder():
            if mode.get()!='월 단위 검증':
                messagebox.showinfo('월 폴더 열기','월 단위 검증에서 월을 선택하세요.',parent=window);return
            try:
                folder=year_folder(path.get(),year.get())/choice.get()
                folder.mkdir(parents=True,exist_ok=True);open_result_file(folder)
            except (ValueError,OSError) as e:messagebox.showerror('월 폴더 열기',str(e),parent=window)
        folder_actions=ttk.Frame(frame);folder_actions.pack(fill='x')
        def reset_month_files():
            if busy:
                messagebox.showinfo('초기화','검증이 끝난 후 초기화하세요.',parent=window);return
            if mode.get()!='월 단위 검증':
                messagebox.showinfo('초기화','월 단위 검증에서 초기화할 월을 선택하세요.',parent=window);return
            from tax_reset import reset_candidates,recycle_inputs
            try:
                if choice.get() not in [f'{m}월' for m in range(1,13)]:raise ValueError('올바른 월을 선택하세요.')
                folder=year_folder(path.get(),year.get())/choice.get()
                files=reset_candidates(folder)
                if not files:
                    messagebox.showinfo('초기화','선택한 월에 초기화할 홈택스·학사 파일이 없습니다.',parent=window);return
                names='\n'.join(p.name for p in files)
                if not messagebox.askyesno('검증 자료 초기화',f'{folder}\n\n다음 {len(files)}개 파일을 휴지통으로 이동할까요?\n{names}\n\n검증 결과·다른 자료·하위 폴더는 유지합니다.',parent=window):return
                moved,failed=recycle_inputs(folder,files)
                status.set(f'{year.get()}년 {choice.get()} 초기화: {len(moved)}개 파일을 휴지통으로 이동했습니다.')
                if failed:messagebox.showwarning('일부 파일 초기화 실패',f'{len(moved)}개 이동 완료\n'+'\n'.join(failed),parent=window)
                else:messagebox.showinfo('초기화 완료',f'{len(moved)}개 파일을 휴지통으로 이동했습니다.\n자료를 다시 내려받아 검증하세요.',parent=window)
            except (ValueError,OSError,ImportError) as exc:messagebox.showerror('초기화 실패',str(exc),parent=window)
        ttk.Button(folder_actions,text='초기화',command=reset_month_files).pack(side='right',padx=(6,0))
        ttk.Button(folder_actions,text='폴더 열기',command=open_month_folder).pack(side='right')
        year=tk.StringVar(value=str(date.today().year))
        year_row=ttk.Frame(frame); year_row.pack(fill='x',pady=12)
        ttk.Label(year_row,text='검증 연도').pack(side='left',padx=(0,10))
        ttk.Spinbox(year_row,from_=1900,to=9999,textvariable=year,width=8).pack(side='left')
        def create_folders():
            try:
                folder=create_year_folders(path.get(),year.get())
                messagebox.showinfo('연도 폴더 준비 완료',f'{folder}\n1월~12월 폴더가 준비되었습니다. 기존 파일은 유지됩니다.',parent=window)
            except (ValueError,OSError) as e:
                messagebox.showerror('폴더 생성 실패',str(e),parent=window)
        def open_offset():
            from tax_invoice_offset import open_picker
            open_picker(window,path.get(),center_window,open_result_file)
        def open_download():
            from hometax_ui import open_hometax
            selected_month=int(choice.get()[:-1]) if mode.get()=='월 단위 검증' else PERIODS[choice.get()][0]
            open_hometax(window,path.get(),year.get(),selected_month,center_window,open_result_file)
        ttk.Button(year_row,text='미처리 상계',command=open_offset).pack(side='right',padx=(8,0))
        ttk.Button(year_row,text='연도 폴더 만들기',command=create_folders).pack(side='right')
        def export_school():
            from school_export_ui import open_school_export
            if mode.get()!='월 단위 검증':
                messagebox.showinfo('학사 자료 저장','월 단위 검증에서 저장할 월을 선택하세요.',parent=window)
                return
            selected_month=int(choice.get()[:-1])
            open_school_export(window,path.get(),year.get(),selected_month,center_window)
        ttk.Button(folder_actions,text='학사 자료 저장',command=export_school).pack(side='left')
        ttk.Button(folder_actions,text='홈택스 자료 내려받기',command=open_download).pack(side='left',padx=8)
        preview=tk.StringVar()
        def update_preview(*_):
            try: preview.set(f'검증 경로: {year_folder(path.get(),year.get())} / 선택한 월')
            except ValueError: preview.set('올바른 연도와 기본 폴더를 입력하세요.')
        year.trace_add('write',update_preview); path.trace_add('write',update_preview)
        update_preview()
        ttk.Label(frame,textvariable=preview,wraplength=610).pack(anchor='w')
        mode=tk.StringVar(value='월 단위 검증'); choice=tk.StringVar(value='1월')
        modes=ttk.Combobox(frame,textvariable=mode,values=['월 단위 검증','신고기간 검증'],state='readonly'); modes.pack(fill='x',pady=15)
        select=ttk.Combobox(frame,textvariable=choice,values=[f'{m}월' for m in range(1,13)],state='readonly'); select.pack(fill='x')
        def change(_):
            values=[f'{m}월' for m in range(1,13)] if mode.get()=='월 단위 검증' else list(PERIODS)
            select.configure(values=values); choice.set(values[0])
        modes.bind('<<ComboboxSelected>>',change)
        ttk.Label(frame,text='학사 자료 저장: 선택한 월의 폴더에 4종을 바로 저장합니다.\n학사 합계표의 조회 기간은 실행 전에 같은 월로 맞춰 두세요.',wraplength=650).pack(anchor='w',pady=(8,0))
        ttk.Label(frame,text='신고기간: 1기예정 1~3월 · 1기확정 4~6월\n2기예정 7~9월 · 2기확정 10~12월\n월별 홈택스·학사 자료 각 4종, 총 8개 파일을 준비하세요.').pack(anchor='w',pady=16)
        status=tk.StringVar(value='검증 후 결과를 자동 저장하고 기본 연결 프로그램으로 엽니다.')
        window._work_status=status
        ttk.Label(frame,textvariable=status,wraplength=610,style='Muted.TLabel').pack(anchor='w')
        messages=queue.Queue(); busy=False
        def close():
            if not busy: window.destroy()
        window.protocol('WM_DELETE_WINDOW',close)
        def poll():
            nonlocal busy
            try: success, result=messages.get_nowait()
            except queue.Empty: window.after(100,poll); return
            busy=False; button.configure(state='normal'); status.set('검증 완료' if success else '자료 확인 필요')
            if success:
                status.set(f'저장 완료: {result}')
                try:
                    open_result_file(result)
                except (OSError, subprocess.SubprocessError) as e:
                    messagebox.showwarning('저장 완료 · 자동 열기 실패',
                        f'결과 파일은 저장되었습니다. 아래 파일을 직접 열어 주세요.\n\n{result}\n\n{e}',parent=window)
            else:
                messagebox.showerror('검증 중단',result,parent=window)
        def execute():
            nonlocal busy
            months=(int(choice.get()[:-1]),) if mode.get()=='월 단위 검증' else PERIODS[choice.get()]
            try: folder=year_folder(path.get(),year.get())
            except ValueError as e:
                messagebox.showerror('연도 설정 확인',str(e),parent=window)
                return
            label=f'{year.get().strip()}_{choice.get()}'
            busy=True; button.configure(state='disabled'); status.set('엑셀 자료를 검증하고 있습니다…')
            def work():
                try: messages.put((True,str(run(folder,months,label))))
                except Exception as e: messages.put((False,str(e)))
            threading.Thread(target=work,daemon=True).start(); window.after(100,poll)
        button=ttk.Button(frame,text='검증 실행  →',command=execute,style='Primary.TButton'); button.pack(fill='x',pady=20)
    def rental_view():
        from rental_ui import open_rentals
        open_rentals(root,desktop,center_window,open_result_file)
    def suspense_view():
        from suspense_ui import open_suspense
        open_suspense(root,desktop,center_window,open_result_file)
    def pending_menu(title):
        window=tk.Toplevel(root,show_on_create=False)
        window.title(title)
        center_window(window,900,600)
        frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text=title,style='Section.TLabel').pack(anchor='w')
        ttk.Label(frame,text='준비 중',style='Muted.TLabel').pack(anchor='w',pady=12)
        window.deiconify()

    def menu_item(title):
        return (title,lambda:pending_menu(title))

    from appendix_view import open_appendix_view
    groups=[
        ('1. 재무제표',[
            ('재무제표 조회',lambda:open_statement_view(root,desktop,center_window,open_result_file)),
            ('부속명세서 조회',lambda:open_appendix_view(root,center_window)),
            ('계정별원장 조회',lambda:open_ledger(root,desktop,center_window,open_result_file)),
            ('합산재무제표 검증',lambda:open_statement_verify(root,desktop,center_window,open_result_file)),
            ('재무제표/부속명세서 검증',lambda:open_statement_verify(root,desktop,center_window,open_result_file,True)),
        ]),
        ('2. 분석도구',[
            menu_item(title) for title in ('재무분석','결산검토','계정과목 검토','차입금관리','임대사항')
        ]),
        ('3. 업무도구',[
            ('세금계산서 검증',open_tax),
            ('예금시재 검증',lambda:open_account(root)),
            ('정기예금 해지계획표',lambda:open_deposit(root,desktop,center_window,open_result_file)),
            ('자금이체 문구 생성',lambda:open_transfer(root,desktop,center_window,open_result_file)),
            ('가수금 정산검증',suspense_view),
        ]),
    ]
    from app_profile import menu_groups,settings_path
    launcher=Launcher(root,menu_groups(groups),settings_path(desktop()/'settings'/'launcher.json'))
    root._launcher=launcher
    from app_profile import beta_label
    if beta_label():print('BETA_MENU_READY='+beta_label()+':'+','.join(title for _,cards in launcher.groups for title,_ in cards),flush=True)
    from update_ui import signal_ready
    from startup_update import check_on_start
    def ready():
        signal_ready()
        check_on_start(root)
    root.after_idle(ready)
    root.mainloop()

if __name__=='__main__': main()
