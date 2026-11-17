"""Expose the borderless launcher in the Windows taskbar."""
import sys

WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000


def taskbar_style(style):
    return (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW


def enable_taskbar(root):
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    get_style = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
    set_style = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL

    def apply(event=None):
        if event is not None and event.widget is not root:
            return
        if not root.winfo_exists() or not root.winfo_ismapped():
            return
        # Tk's native wrapper, rather than its inner drawing window, owns the taskbar entry.
        hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT
        if not hwnd:
            return
        old = get_style(hwnd, -20)  # GWL_EXSTYLE
        new = taskbar_style(old)
        if new == old:
            return
        ctypes.set_last_error(0)
        set_style(hwnd, -20, new)
        if ctypes.get_last_error():
            return
        # Re-register the changed shell style without taking focus from another window.
        user32.ShowWindow(hwnd, 0)  # SW_HIDE
        user32.ShowWindow(hwnd, 8)  # SW_SHOWNA

    root.bind('<Map>', apply, add='+')
    root.after_idle(apply)
