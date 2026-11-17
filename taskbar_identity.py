"""A version-independent identity shared by the launcher and installed shortcuts."""
import ctypes
import sys

APP_USER_MODEL_ID = 'WorkSpace.Desktop'


def set_taskbar_identity():
    """Call before creating windows; shell integration must not block startup."""
    if sys.platform != 'win32':
        return False
    try:
        api = ctypes.WinDLL('shell32', use_last_error=True)
        api.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        api.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        return api.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID) == 0
    except (OSError, AttributeError):
        return False
