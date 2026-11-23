"""Shared version status and Setup download link for the workspace and compact menu."""
from html import escape
import qt_ui as tk
from app_version import current_version


def version_status(root):
    root=root._root()
    if not hasattr(root,'_version_status'):
        version=current_version() or '확인 불가'
        root._version_status=tk.StringVar(value=f'현재 {version} · 최신 버전 확인 대기')
    return root._version_status


def bind_status_label(root,label):
    variable=version_status(root)
    def refresh(*_):
        if not root.winfo_exists() or not tk.isValid(label):return
        value=variable.get()
        url=getattr(root._root(),'_setup_download_url',None)
        label.setTextFormat(tk.C.Qt.TextFormat.RichText if url else tk.C.Qt.TextFormat.PlainText)
        if url:value=escape(value)+f' · <a href="{escape(url,quote=True)}">Setup 다운로드</a>'
        label.setText(value)
    label.setTextInteractionFlags(tk.C.Qt.TextInteractionFlag.TextBrowserInteraction)
    label.setOpenExternalLinks(True)
    token=variable.trace_add('write',refresh)
    label.destroyed.connect(lambda *_:variable.trace_remove('write',token))
    refresh()
