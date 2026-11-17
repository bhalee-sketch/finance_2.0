"""Non-modal file reads: workers receive snapshots, Qt updates stay on the GUI thread."""
import queue
import threading
import qt_ui as q


class BackgroundRead:
    def __init__(self,window,status):
        self.window=window;self.status=status;self.busy=False
        window._read_task=self
        window.protocol('WM_DELETE_WINDOW',self.close)

    def close(self):
        if self.busy:self.status.set('자료를 읽고 있습니다. 완료 후 화면을 닫을 수 있습니다.')
        else:self.window.destroy()

    def run(self,work,done,failed):
        if self.busy or not self.window.winfo_exists():return False
        self.busy=True;messages=queue.Queue()
        controls=self.window._q.findChildren(q.W.QWidget)
        states=[(w,w.isEnabled()) for w in controls if isinstance(w,(q.W.QAbstractButton,q.W.QLineEdit,q.W.QComboBox,q.W.QAbstractSpinBox))]
        for w,_ in states:w.setEnabled(False)
        self.status.set('계좌 자료를 읽고 있습니다… 다른 업무는 계속 사용할 수 있습니다.')
        def worker():
            try:messages.put((True,work()))
            except Exception as exc:messages.put((False,exc))
        def poll():
            if not self.window.winfo_exists():return
            try:ok,result=messages.get_nowait()
            except queue.Empty:self.window.after(50,poll);return
            self.busy=False
            for w,enabled in states:
                if q.isValid(w):w.setEnabled(enabled)
            try:
                if ok:done(result)
                else:failed(result)
            except Exception as exc:
                self.status.set('결과 표시 확인 필요');q.messagebox.showerror('결과 확인',str(exc),parent=self.window)
        threading.Thread(target=worker,daemon=True).start();self.window.after(50,poll)
        return True
