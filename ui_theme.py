"""Application-wide Qt style, with reversible light/dark preferences."""
BG='#0D1420';PANEL='#172231';TEXT='#E2E8F0';MUTED='#94A3B8';ACCENT='#93C5FD'

def qt_stylesheet(theme='light'):
    from pathlib import Path
    arrow=(Path(__file__).resolve().parent/'assets'/'chevron-down.svg').as_posix()
    light=theme=='light'
    bg='#F5F2FA' if light else '#171422';panel='#FFFFFF' if light else '#231F30';text='#403B4A' if light else '#EAE5F4';muted='#696174' if light else '#ADA4BF';border='#E9E3F0' if light else '#3A324D';accent='#7651AD' if light else '#B99AEF';selection='#E9DFF7' if light else '#44345D';stripe='#FAF8FD' if light else '#292435';button_text='#FFFFFF' if light else '#211A2D'
    return f'''
QWidget {{ color:{text}; background-color:{panel}; }}
QLabel {{ background:transparent; }}
QLabel[role="Title.TLabel"] {{ font-size:24pt; font-weight:700; }}
QLabel[role="Section.TLabel"] {{ font-size:16pt; font-weight:600; }}
QLabel[role="Muted.TLabel"] {{ color:{muted}; }}
QLabel[role="Accent.TLabel"] {{ color:{accent}; font-weight:600; }}
QPushButton {{ background:{panel}; border:1px solid {border}; border-radius:8px; padding:7px 12px; min-height:18px; }}
QPushButton:hover {{ border-color:{accent}; background:{selection}; }}
QPushButton:focus,QToolButton:focus {{ outline:2px solid {accent}; }}
QPushButton:pressed {{ background:{selection}; }}
QPushButton:disabled {{ color:{muted}; }}
QPushButton[role="Primary.TButton"] {{ background:{accent}; color:{button_text}; font-weight:600; border-color:{accent}; }}
QLineEdit,QComboBox,QTextEdit,QListWidget {{ background:{panel}; border:1px solid {border}; border-radius:5px; padding:5px 7px; selection-background-color:{selection}; }}
QLineEdit:focus,QComboBox:focus,QTextEdit:focus {{ border-color:{accent}; }}
QComboBox {{ padding-right:28px; combobox-popup:0; }}
QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:top right; border:0; width:24px; }}
QComboBox::down-arrow {{ image:url("{arrow}"); width:12px; height:12px; }}
QComboBox QAbstractItemView {{ background:{panel}; color:{text}; selection-background-color:{selection}; selection-color:{text}; outline:0; }}
QComboBox QAbstractItemView::item:hover,QComboBox QAbstractItemView::item:selected {{ background:{selection}; color:{text}; }}
QGroupBox {{ border:1px solid {border}; border-radius:6px; margin-top:12px; padding:10px; }}
QGroupBox::title {{ subcontrol-origin:margin; left:10px; padding:0 4px; color:{muted}; }}
QTableView:focus {{ border-color:{accent}; }}
QTableView {{ background:{panel}; alternate-background-color:{stripe}; border:1px solid {border}; gridline-color:{border}; selection-background-color:{selection}; selection-color:{text}; }}
QHeaderView::section {{ background:{panel}; color:{muted}; border:0; border-bottom:1px solid {border}; border-right:1px solid {border}; padding:8px; font-weight:600; }}
QTabWidget::pane {{ border:1px solid {border}; border-radius:5px; }}
QTabBar::tab {{ padding:9px 14px; border-bottom:2px solid transparent; }}
QTabBar::tab:selected {{ color:{accent}; border-bottom-color:{accent}; background:{panel}; }}
QScrollBar:vertical {{ width:12px; background:{bg}; }}
QScrollBar:horizontal {{ height:12px; background:{bg}; }}
QScrollBar::handle {{ background:{border}; border-radius:5px; min-height:24px; min-width:24px; }}
QScrollBar::add-line,QScrollBar::sub-line {{ width:0; height:0; }}
QProgressBar {{ border:0; background:{panel}; min-height:5px; text-align:center; }}
QProgressBar::chunk {{ background:{accent}; }}
QToolTip {{ background:{panel}; border:1px solid {border}; color:{text}; padding:6px; }}
QWidget#WorkspaceChrome {{ background:{bg}; border:1px solid {border}; border-radius:16px; }}
QFrame#WorkspaceTopbar,QFrame#WorkspaceStatusbar {{ background:{bg}; border:0; }}
QLabel#WorkspaceBrand {{ background:{panel}; color:{accent}; font-size:13pt; font-weight:700; border-radius:8px; }}
QFrame#WorkspaceSidebar {{ background:{panel}; border:1px solid {border}; border-radius:13px; }}
QWidget#WorkspaceHomePanel {{ background:{panel}; border-radius:13px; }}
QTabWidget#WorkspacePages::pane {{ background:{panel}; border:1px solid {border}; border-radius:13px; }}
QTabBar#WorkspaceTabs {{ background:transparent; }}
QTabBar#WorkspaceTabs::tab {{ background:transparent; color:{muted}; padding:8px 15px; margin:0 2px; border:0; border-radius:8px; min-width:40px; }}
QTabBar#WorkspaceTabs::tab:selected {{ background:{panel}; color:{accent}; font-weight:400; }}
QTabBar#WorkspaceTabs[homeActive="true"]::tab:selected {{ background:transparent; color:{muted}; }}
QToolButton#WorkspaceHomeButton:checked {{ background:{selection}; }}
QTabBar#WorkspaceTabs::tab:hover {{ background:{selection}; }}
QLabel#WorkspaceLocalBadge {{ background:{selection}; color:{accent}; border-radius:9px; padding:4px 9px; font-size:10pt; }}
QToolButton {{ background:transparent; color:{muted}; border:0; border-radius:6px; padding:5px 8px; }}
QPushButton[role="Caution.TButton"] {{ color:{text}; border-color:{accent}; }}
QToolButton:hover {{ background:{selection}; color:{accent}; }}
QLabel#WorkspaceSection {{ color:{muted}; font-size:10pt; padding:4px 5px; }}
QLabel#WorkspaceMuted {{ color:{muted}; background:transparent; font-size:10pt; }}
QTreeView#WorkspaceNavigation {{ font-weight:400; border:0; background:{panel}; outline:0; show-decoration-selected:0; }}
QTreeView#WorkspaceNavigation::item {{ padding:7px 3px; border:0; border-radius:0; }}
QTreeView#WorkspaceNavigation::branch {{ background:transparent; border:0; }}
QTreeView#WorkspaceNavigation::item:hover {{ background:{bg}; }}
QTreeView#WorkspaceNavigation::item:selected {{ background:{selection}; color:{accent}; }}
QPushButton#WorkspaceSideTool {{ border:0; text-align:left; color:{muted}; }}
QLineEdit#WorkspaceSearch {{ border:1px solid {border}; border-radius:9px; padding:8px; selection-background-color:{selection}; }}
QLineEdit#WorkspaceSearch:focus {{ border-color:{accent}; }}
QPushButton#WorkspaceOpenButton {{ color:{accent}; background:{selection}; border:0; }}
QTableView#WorkspaceList {{ border:0; background:{panel}; selection-background-color:{selection}; outline:0; }}
QTableView#WorkspaceList::item {{ border:0; padding:8px; }}
QTableView#WorkspaceList QHeaderView::section {{ border:0; border-bottom:1px solid {border}; background:{panel}; color:{muted}; padding:10px 8px; font-size:10pt; font-weight:400; }}
QSplitter#WorkspaceSplit::handle {{ background:{bg}; width:8px; }}

'''

def apply_theme(root):
    from appearance import set_appearance
    set_appearance(root,'light','Paperlogy')

def dark_titlebar(window):
    """Keep native Windows controls, with colors matching the application theme."""
    import sys
    if sys.platform!='win32' or not window._q.isWindow():return
    import ctypes
    from ctypes import wintypes
    from appearance import controller
    appearance=controller(window)
    light=appearance is None or appearance.theme=='light'
    def colorref(value):
        r,g,b=bytes.fromhex(value.lstrip('#'));return r|(g<<8)|(b<<16)
    try:
        apply=ctypes.windll.dwmapi.DwmSetWindowAttribute
        apply.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
        apply.restype=ctypes.c_long
        hwnd=window.winfo_id()
        for attribute,value in ((20,int(not light)),(35,colorref('#F5F2FA' if light else '#171422')),(36,colorref('#403B4A' if light else '#EAE5F4'))):
            data=wintypes.DWORD(value)
            apply(hwnd,attribute,ctypes.byref(data),ctypes.sizeof(data))
        # Older Windows builds may not support caption colors; retain native controls.
    except (AttributeError,OSError):pass
