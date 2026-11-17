"""Win32 adapter. All mouse actions are scoped to the calibrated foreground process."""
import ctypes as C
from ctypes import wintypes as W
import os
import time
from pathlib import Path
from school_export import ExportError, validate_profile, default_profile


class WindowsSchool:
    def __init__(self):
        if os.name != 'nt':
            raise ExportError('학사 자료 저장은 Windows PC에서 실행하세요.')
        self.u = C.WinDLL('user32', use_last_error=True)
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        signatures = {
            'GetForegroundWindow': ([], W.HWND),
            'GetWindow': ([W.HWND, W.UINT], W.HWND),
            'SetForegroundWindow': ([W.HWND], W.BOOL),
            'ShowWindow': ([W.HWND, C.c_int], W.BOOL),
            'GetAncestor': ([W.HWND, W.UINT], W.HWND),
            'GetWindowThreadProcessId': ([W.HWND, C.POINTER(W.DWORD)], W.DWORD),
            'GetClientRect': ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            'GetWindowRect': ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            'ClientToScreen': ([W.HWND, C.POINTER(W.POINT)], W.BOOL),
            'GetCursorPos': ([C.POINTER(W.POINT)], W.BOOL),
            'WindowFromPoint': ([W.POINT], W.HWND),
            'GetClassNameW': ([W.HWND, W.LPWSTR, C.c_int], C.c_int),
            'IsWindow': ([W.HWND], W.BOOL),
            'IsWindowVisible': ([W.HWND], W.BOOL),
            'IsIconic': ([W.HWND], W.BOOL),
            'GetAsyncKeyState': ([C.c_int], C.c_short),
            'SetCursorPos': ([C.c_int, C.c_int], W.BOOL),
            'mouse_event': ([W.DWORD, W.DWORD, W.DWORD, W.DWORD, C.c_size_t], None),
            'EnumWindows': ([self.callback, W.LPARAM], W.BOOL),
            'EnumChildWindows': ([W.HWND, self.callback, W.LPARAM], W.BOOL),
            'GetDlgItem': ([W.HWND, C.c_int], W.HWND),
            'GetMenuItemCount': ([W.HMENU], C.c_int),
            'GetMenuStringW': ([W.HMENU, W.UINT, W.LPWSTR, C.c_int, W.UINT], C.c_int),
            'GetMenuItemRect': ([W.HWND, W.HMENU, W.UINT, C.POINTER(W.RECT)], W.BOOL),
            'SendMessageTimeoutW': ([W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.POINTER(C.c_size_t)], C.c_ssize_t),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.u, name); fn.argtypes = args; fn.restype = result
        self.k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; self.k.OpenProcess.restype = W.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.k.CloseHandle.argtypes = [W.HANDLE]
        self.hwnd = None

    def pid(self, hwnd):
        value = W.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, C.byref(value))
        return value.value

    def process(self, hwnd):
        handle = self.k.OpenProcess(0x1000, False, self.pid(hwnd))
        if not handle:
            raise ExportError('학사 프로세스를 읽을 수 없습니다. 두 프로그램의 실행 권한을 확인하세요.')
        try:
            buf = C.create_unicode_buffer(32768); size = W.DWORD(len(buf))
            if not self.k.QueryFullProcessImageNameW(handle, 0, buf, C.byref(size)):
                raise ExportError('실행 파일 경로를 확인하지 못했습니다.')
            return Path(buf.value).name.lower()
        finally:
            self.k.CloseHandle(handle)

    def class_name(self, hwnd):
        buf = C.create_unicode_buffer(256); self.u.GetClassNameW(hwnd, buf, len(buf))
        return buf.value

    def dpi(self, hwnd):
        if not hasattr(self.u, 'GetDpiForWindow'):
            return 96
        self.u.GetDpiForWindow.argtypes = [W.HWND]; self.u.GetDpiForWindow.restype = W.UINT
        return self.u.GetDpiForWindow(hwnd)

    def geometry(self, hwnd):
        rect = W.RECT(); origin = W.POINT()
        if not self.u.GetClientRect(hwnd, C.byref(rect)) or not self.u.ClientToScreen(hwnd, C.byref(origin)):
            raise ExportError('학사 창 위치를 읽지 못했습니다.')
        return (origin.x, origin.y), [rect.right, rect.bottom]

    def capture(self):
        hwnd = self.u.GetAncestor(self.u.GetForegroundWindow(), 2)
        if self.process(hwnd) not in ('hguniv.exe', '학사정보시스템.exe'):
            raise ExportError('학사 합계표 창을 활성화한 후 다시 지정하세요.')
        if self.class_name(hwnd) == '#32770':
            raise ExportError('저장창을 닫고 합계표 창에서 위치를 지정하세요.')
        origin, size = self.geometry(hwnd)
        cursor = W.POINT(); self.u.GetCursorPos(C.byref(cursor))
        if self.pid(self.u.WindowFromPoint(cursor)) != self.pid(hwnd):
            raise ExportError('마우스를 학사 창 안의 해당 버튼 위에 놓으세요.')
        point = [cursor.x - origin[0], cursor.y - origin[1]]
        if not (0 <= point[0] < size[0] and 0 <= point[1] < size[1]):
            raise ExportError('학사 창 내부의 위치를 지정하세요.')
        return {'size': size, 'dpi': self.dpi(hwnd)}, point

    def activate_default(self, stop):
        candidates = []
        @self.callback
        def collect(hwnd, _):
            if not self.u.IsWindowVisible(hwnd) or self.u.GetWindow(hwnd, 4) or self.class_name(hwnd) in ('#32770', '#32768'):
                return True
            try:
                if self.process(hwnd) in ('hguniv.exe', '학사정보시스템.exe'):
                    candidates.append(hwnd)
            except ExportError:
                pass
            return True
        self.u.EnumWindows(collect, 0)
        if len(candidates) != 1:
            raise ExportError('실행 중인 학사 기본 창을 하나만 열어 두세요. 합계표 메뉴를 먼저 열어야 합니다.')
        hwnd = candidates[0]
        if stop.is_set():
            raise ExportError('사용자가 중단했습니다.')
        if self.u.IsIconic(hwnd):
            self.u.ShowWindow(hwnd, 9)
        if not self.u.SetForegroundWindow(hwnd):
            raise ExportError('학사 창을 활성화하지 못했습니다. 학사 창을 확인한 뒤 다시 실행하세요.')
        if stop.wait(.3):
            raise ExportError('사용자가 중단했습니다.')
        _, size = self.geometry(hwnd)
        self.attach(default_profile(size, self.dpi(hwnd)))

    def capture_menu(self, profile):
        self.attach(profile)
        cursor = W.POINT()
        self.u.GetCursorPos(C.byref(cursor))
        popup = self.u.GetAncestor(self.u.WindowFromPoint(cursor), 2)
        if self.pid(popup) != self.owner or self.class_name(popup) != '#32768':
            raise ExportError('상단 표를 우클릭한 뒤 기본엑셀 항목 위에 마우스를 놓으세요.')
        rect = W.RECT()
        if not self.u.GetWindowRect(popup, C.byref(rect)):
            raise ExportError('우클릭 메뉴 위치를 읽지 못했습니다.')
        return {'size': [rect.right-rect.left, rect.bottom-rect.top],
                'point': [cursor.x-rect.left, cursor.y-rect.top]}

    def attach(self, profile):
        validate_profile(profile)
        hwnd = self.u.GetAncestor(self.u.GetForegroundWindow(), 2)
        if self.process(hwnd) not in ('hguniv.exe', '학사정보시스템.exe') or self.class_name(hwnd) == '#32770':
            raise ExportError('학사 합계표 창을 활성화해 두세요.')
        self.hwnd, self.owner, self.profile = hwnd, self.pid(hwnd), profile
        self.check()

    def escape_pressed(self):
        return bool(self.u.GetAsyncKeyState(0x1B) & 0x8000)

    def check(self):
        if not self.u.IsWindow(self.hwnd) or self.u.IsIconic(self.hwnd):
            raise ExportError('학사 창이 닫히거나 최소화되어 중단했습니다.')
        if self.pid(self.u.GetForegroundWindow()) != self.owner:
            raise ExportError('다른 창으로 전환되어 중단했습니다. 학사 합계표를 활성화하고 다시 실행하세요.')
        _, size = self.geometry(self.hwnd)
        if size != self.profile['size'] or self.dpi(self.hwnd) != self.profile['dpi']:
            raise ExportError('창 크기 또는 화면 배율이 바뀌었습니다. 위치를 다시 지정하세요.')

    def windows(self, parent=None):
        result = []
        @self.callback
        def collect(hwnd, _):
            if self.u.IsWindowVisible(hwnd) and self.pid(hwnd) == self.owner:
                result.append(hwnd)
            return True
        if parent is None:
            self.u.EnumWindows(collect, 0)
        else:
            self.u.EnumChildWindows(parent, collect, 0)
        return result

    def message(self, hwnd, code, wp=0, lp=0):
        result = C.c_size_t()
        if not self.u.SendMessageTimeoutW(hwnd, code, wp, lp, 2, 1500, C.byref(result)):
            raise ExportError('학사 창 응답을 확인하지 못했습니다. 실행 권한과 창 상태를 확인하세요.')
        return result.value

    def text(self, hwnd):
        buf = C.create_unicode_buffer(32768)
        self.message(hwnd, 0xD, len(buf), C.addressof(buf))
        return buf.value

    def mouse(self, x, y, right=False, target=None):
        self.check()
        hit = self.u.WindowFromPoint(W.POINT(x, y))
        if self.pid(hit) != self.owner:
            raise ExportError('클릭 위치가 다른 창에 가려져 중단했습니다.')
        if target and self.u.GetAncestor(hit, 2) != target:
            raise ExportError('예상한 창이 아닌 위치여서 중단했습니다.')
        self.u.SetCursorPos(x, y)
        down, up = (8, 16) if right else (2, 4)
        self.u.mouse_event(down, 0, 0, 0, 0)
        self.u.mouse_event(up, 0, 0, 0, 0)

    def click(self, label):
        self.check()
        if self.u.GetAncestor(self.u.GetForegroundWindow(), 2) != self.hwnd:
            raise ExportError('학사 팝업이 열려 있어 중단했습니다. 팝업 내용을 확인하세요.')
        origin, _ = self.geometry(self.hwnd)
        x, y = self.profile['points'][label]
        self.mouse(origin[0] + x, origin[1] + y, label == '상단 합계표', self.hwnd)

    def wait_for(self, finder, check, message):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            check()
            found = finder()
            if found:
                return found
            time.sleep(.1)
        raise ExportError(message)

    def ready(self):
        self.check()
        # WM_NULL must be processed by the UI thread before the export menu opens.
        self.message(self.hwnd, 0)
        if self.u.GetAncestor(self.u.GetForegroundWindow(), 2) != self.hwnd:
            raise ExportError('조회 후 팝업이 열렸습니다. 내용을 확인하고 다시 실행하세요.')

    def open_excel(self, check):
        self.click('상단 합계표')
        if self.profile.get('excel_menu'):
            def find_popup():
                popups = [w for w in self.windows() if self.class_name(w) == '#32768']
                return popups[0] if len(popups) == 1 else None
            popup = self.wait_for(find_popup, check, '학사 우클릭 메뉴가 하나만 열린 상태인지 확인하세요.')
            check()
            rect = W.RECT()
            if not self.u.GetWindowRect(popup, C.byref(rect)):
                raise ExportError('우클릭 메뉴 위치를 읽지 못했습니다.')
            x, y = menu_position(self.profile['excel_menu'], rect)
            self.mouse(x, y, target=popup)
            return
        def find():
            for popup in self.windows():
                if self.class_name(popup) != '#32768':
                    continue
                menu = self.message(popup, 0x1E1)  # MN_GETHMENU: native popup menu only
                for i in range(max(0, self.u.GetMenuItemCount(menu))):
                    buf = C.create_unicode_buffer(256)
                    self.u.GetMenuStringW(menu, i, buf, len(buf), 0x400)
                    if buf.value.replace('&', '').replace(' ', '').split('\t')[0] == '기본엑셀':
                        rect = W.RECT()
                        if self.u.GetMenuItemRect(None, menu, i, C.byref(rect)):
                            return rect
            return None
        rect = self.wait_for(find, check, '우클릭 메뉴에서 기본엑셀을 인식하지 못했습니다. 상단 표 위치를 확인하세요.')
        check(); self.mouse((rect.left + rect.right)//2, (rect.top + rect.bottom)//2)

    def save_as(self, path, check):
        def find():
            for window in self.windows():
                if self.class_name(window) != '#32770':
                    continue
                title = self.text(window).replace(' ', '')
                if '저장' not in title:
                    continue
                edit = self.u.GetDlgItem(window, 0x480)  # edt1, classic Save As
                if not edit or self.class_name(edit).lower() != 'edit':
                    combo = self.u.GetDlgItem(window, 0x47C)  # cmb13, Explorer Save As
                    edits = [c for c in self.windows(combo) if self.class_name(c).lower() == 'edit'] if combo else []
                    edit = edits[0] if len(edits) == 1 else None
                button = self.u.GetDlgItem(window, 1)
                if edit and button and '저장' in self.text(button):
                    return window, edit, button
            return None
        dialog, edit, button = self.wait_for(find, check, '파일 저장창의 파일 이름/저장 버튼을 인식하지 못했습니다.')
        check()
        if self.u.GetAncestor(self.u.GetForegroundWindow(), 2) != dialog:
            raise ExportError('저장창이 활성 상태가 아닙니다.')
        value = str(path.resolve())
        buffer = C.create_unicode_buffer(value)
        self.message(edit, 0xC, 0, C.addressof(buffer))  # WM_SETTEXT: marshalled by Windows
        if self.text(edit) != value:
            raise ExportError('저장 파일명 입력이 확인되지 않았습니다.')
        check()
        rect = W.RECT(); self.u.GetWindowRect(button, C.byref(rect))
        self.mouse((rect.left + rect.right)//2, (rect.top + rect.bottom)//2, target=dialog)


def menu_position(calibration, rect):
    """Use menu-relative coordinates so screen-edge repositioning is supported."""
    try:
        actual_size = [rect.right-rect.left, rect.bottom-rect.top]
        width, height = calibration.get('size', actual_size)
        x, y = calibration['point']
        if actual_size != [width, height] or not (0 <= x < width and 0 <= y < height):
            raise ValueError()
        return rect.left+x, rect.top+y
    except (KeyError, TypeError, ValueError):
        raise ExportError('우클릭 메뉴 크기/구성이 달라졌습니다. 기본엑셀 위치를 다시 지정하세요.') from None
