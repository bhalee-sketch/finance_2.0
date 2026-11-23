"""Exercise the interactive Windows update wizard in the release smoke test."""
import ctypes
from ctypes import wintypes
import subprocess
import sys
import time


def verify_setup(installer, folder):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    window_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [window_callback, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetDlgItem.restype = wintypes.HWND
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_void_p,
        wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
    ]
    user32.SendMessageTimeoutW.restype = wintypes.LPARAM
    user32.IsWindowEnabled.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    command = subprocess.list2cmdline([installer, '/AUTORESTART=1']) + ' /D=' + folder
    process = subprocess.Popen(command, executable=installer)

    def click_page(label, timeout):
        matched = None

        @window_callback
        def find_button(hwnd, _):
            nonlocal matched
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != process.pid or not user32.IsWindowVisible(hwnd):
                return True
            button = user32.GetDlgItem(hwnd, 1)
            if not button or not user32.IsWindowEnabled(button):
                return True
            text = ctypes.create_unicode_buffer(80)
            user32.SendMessageTimeoutW(button, 0x000D, len(text), text, 0x0002, 1000, None)  # WM_GETTEXT
            if text.value.replace('&', '').strip() == label:
                matched = hwnd, button
                return False
            return True

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and process.poll() is None:
            user32.EnumWindows(find_button, 0)
            if matched is not None:
                hwnd, button = matched
                if not user32.PostMessageW(hwnd, 0x0111, 1, button):  # WM_COMMAND / IDOK
                    raise ctypes.WinError(ctypes.get_last_error())
                return
            time.sleep(.2)
        raise RuntimeError(f'Setup did not show the {label} button.')

    try:
        click_page('설치', 30)
        click_page('마침', 120)
        if process.wait(timeout=25) != 0:
            raise RuntimeError('Setup did not exit successfully.')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


if __name__ == '__main__':
    verify_setup(*sys.argv[1:])
