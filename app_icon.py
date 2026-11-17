"""Use the bundled Work Space icon for the main window and child windows."""
from pathlib import Path
import sys
import qt_ui as tk


def apply_app_icon(root):
    assets = Path(__file__).resolve().parent / 'assets'
    try:
        icon=tk.G.QIcon(str(assets / 'workspace.ico'))
        if not icon.isNull():tk.application().setWindowIcon(icon)
        if sys.platform == 'win32':
            root.iconbitmap(default=str(assets / 'workspace.ico'))
        else:
            root._workspace_icon = tk.PhotoImage(file=str(assets / 'workspace.png'))
            root.iconphoto(True, root._workspace_icon)
    except (tk.TclError, OSError):
        # An unavailable icon must never prevent the application from starting.
        pass
