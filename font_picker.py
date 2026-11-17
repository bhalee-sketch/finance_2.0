"""Search installed font families, preview and register a chosen family."""
import qt_ui as tk
from qt_ui import ttk,font as tkfont


def open_font_picker(parent,on_add):
    previous_grab=parent.grab_current()
    dialog=tk.Toplevel(parent,show_on_create=False);dialog.title('글꼴 검색 · 추가');dialog.transient(parent);dialog.geometry('540x500')
    body=ttk.Frame(dialog,padding=16);body.pack(fill='both',expand=True)
    query=tk.StringVar();entry=ttk.Entry(body,textvariable=query);entry.pack(fill='x')
    ttk.Label(body,text='설치된 글꼴 이름을 검색하고 선택하세요.').pack(anchor='w',pady=6)
    frame=ttk.Frame(body);frame.pack(fill='both',expand=True)
    items=tk.Listbox(frame,exportselection=False);items.pack(side='left',fill='both',expand=True)
    bar=ttk.Scrollbar(frame,command=items.yview);bar.pack(side='right',fill='y');items.configure(yscrollcommand=bar.set)
    sample=ttk.Label(body,text='가나다 ABC 0123456789\n1,234,567원',padding=12);sample.pack(fill='x')
    families=sorted(set(tkfont.families(parent)),key=str.casefold)
    def search(*_):
        items.delete(0,'end')
        for family in families:
            if query.get().strip().casefold() in family.casefold():items.insert('end',family)
    def preview(event=None):
        selected=items.curselection()
        if selected:
            # A named font bypasses the application font substitution only for this sample.
            sample._preview_font=tkfont.Font(root=dialog,family=items.get(selected[0]),size=16)
            sample.configure(font=sample._preview_font)
    def add():
        selected=items.curselection()
        if selected:on_add(items.get(selected[0]));dialog.destroy()
    items.bind('<<ListboxSelect>>',preview);items.bind('<Double-1>',lambda event:add())
    ttk.Button(body,text='선택한 글꼴 추가',command=add).pack(side='right',pady=8)
    query.trace_add('write',search);search()
    def restore(event=None):
        if event is None or event.widget is dialog:
            if previous_grab is not None and previous_grab.winfo_exists():previous_grab.grab_set()
    dialog.bind('<Destroy>',restore)
    dialog.update_idletasks();dialog.deiconify();dialog.grab_set();entry.focus_set()
    return dialog
