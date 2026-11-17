"""One-time private repository binding; network and vault calls never run on Qt's thread."""
import queue
import threading
import qt_ui as q
from release_update import API,GithubClient
from token_store import save_windows_credential
from version_status import version_status


def request_credentials(root,on_saved):
    existing=getattr(root,'_update_credentials_dialog',None)
    if existing is not None and q.isValid(existing):existing.show();existing.raise_();return existing
    messages=queue.Queue();cancel=threading.Event()
    class BindingDialog(q.W.QDialog):
        busy=False
        def reject(self):
            if not self.busy:
                version_status(root).set('자동 업데이트 인증 미설정 · 다음 실행 시 다시 확인')
                super().reject()
        def closeEvent(self,event):
            if self.busy:event.ignore()
            else:super().closeEvent(event)
    dialog=BindingDialog(root._q);root._update_credentials_dialog=dialog
    dialog.setAttribute(q.C.Qt.WidgetAttribute.WA_DeleteOnClose,True)
    dialog.setWindowTitle('자동 업데이트 · 최초 인증 설정');dialog.setMinimumWidth(430)
    layout=q.W.QVBoxLayout(dialog);layout.setContentsMargins(20,20,20,20);layout.setSpacing(12)
    info=q.W.QLabel('GitHub 배포에 접근할 수 없습니다. 비공개 저장소의 접근 토큰을 한 번 저장하면 이후 실행부터 자동 업데이트합니다.\n\n이 저장소의 Contents 읽기 권한이 필요합니다. 토큰은 이 PC의 Windows 자격 증명 관리자에 저장됩니다.')
    info.setWordWrap(True);layout.addWidget(info)
    label=q.W.QLabel('GitHub 접근 토큰');layout.addWidget(label)
    entry=q.W.QLineEdit();entry.setEchoMode(q.W.QLineEdit.EchoMode.Password);entry.setMaxLength(1280)
    entry.setAccessibleName('GitHub 접근 토큰');label.setBuddy(entry);layout.addWidget(entry)
    notice=q.W.QLabel('인증 확인과 저장 중에도 다른 업무를 사용할 수 있습니다.');notice.setWordWrap(True);layout.addWidget(notice)
    row=q.W.QHBoxLayout();later=q.W.QPushButton('나중에');save=q.W.QPushButton('확인하고 한 번 저장')
    save.setProperty('role','Primary.TButton');row.addWidget(later);row.addStretch();row.addWidget(save);layout.addLayout(row)
    timer=q.C.QTimer(dialog);timer.setInterval(100)
    dialog.destroyed.connect(lambda *_:cancel.set())
    later.clicked.connect(dialog.reject)
    def submit():
        if dialog.busy:return
        token=entry.text().strip()
        if not token:notice.setText('접근 토큰을 입력하세요.');entry.setFocus();return
        dialog.busy=True;entry.clear();entry.setEnabled(False);save.setEnabled(False);later.setEnabled(False)
        notice.setText('GitHub 읽기 권한을 확인하고 안전하게 저장하는 중…')
        def worker():
            try:
                releases=GithubClient(token).json(API+'/releases?per_page=1')
                if not isinstance(releases,list):raise ValueError('Invalid response')
                if cancel.is_set():return
                save_windows_credential(token)
                messages.put(True)
            except Exception:
                # Never display exception text that might contain credentials.
                if not cancel.is_set():messages.put(False)
        threading.Thread(target=worker,daemon=True).start();timer.start()
    def poll():
        try:ok=messages.get_nowait()
        except queue.Empty:return
        timer.stop();dialog.busy=False
        if ok:
            dialog.accept();on_saved()
        else:
            entry.setEnabled(True);save.setEnabled(True);later.setEnabled(True);entry.setFocus()
            notice.setText('인증 확인 또는 저장에 실패했습니다. 인터넷 연결, 토큰 만료일과 저장소 Contents 읽기 권한을 확인하고 다시 입력하세요.')
    timer.timeout.connect(poll);save.clicked.connect(submit);entry.returnPressed.connect(submit)
    # Non-modal: no exec(), grab, or synchronous network request.
    dialog.show();entry.setFocus()
    return dialog
