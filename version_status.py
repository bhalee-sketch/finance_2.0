"""Shared version status for the workspace and compact menu."""
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
        label.setText(variable.get())
    token=variable.trace_add('write',refresh)
    label.destroyed.connect(lambda *_:variable.trace_remove('write',token))
    refresh()
