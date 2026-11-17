"""Application-scoped Qt appearance settings for widgets and graphics charts.

Retain original dark colors/fonts so changing themes is reversible. Workbooks,
images and other non-Tk output are never transformed.
"""
import colorsys
import re
import weakref
import qt_ui as tk
from qt_ui import ttk,font as tkfont

DEFAULT_FONT='Paperlogy'
LIGHT={
    '#FDE8E8':'#FDE8E8','#7F1D1D':'#7F1D1D',
    '#0D1420':'#F5F2FA','#172231':'#FFFFFF','#223653':'#F0EAFA',
    '#E2E8F0':'#172638','#94A3B8':'#928B9E','#93C5FD':'#9574D2',
    '#1F77B4':'#1F77B4','#FF7F0E':'#D96100','#2CA02C':'#238323',
    '#D62728':'#D62728','#9467BD':'#8652AD','#17BECF':'#088595',
    '#E377C2':'#B64094','#BCBD22':'#838411','#8C564B':'#8C564B',
    '#4E79A7':'#4E79A7','#59A14F':'#377E30',
    '#10141E':'#F4F6FA','#101722':'#F4F6FA','#192131':'#FFFFFF','#192738':'#FFFFFF',
    '#17212F':'#FFFFFF','#1B293D':'#F5F8FC','#1D3049':'#EFF5FC','#203248':'#EFF5FC',
    '#253247':'#F8F6FC','#253C54':'#F8F6FC','#31546B':'#F0EAFA','#244C70':'#D8E9FA',
    '#245B70':'#C9E1FA','#203B53':'#E4EFF9','#284258':'#C9DDF0','#22354B':'#E1EAF5',
    '#354B64':'#C6D7EB','#30435D':'#D8E4F3','#1B2331':'#E9EDF3','#151C28':'#EEF1F5',
    '#36445B':'#A7B6CA','#3A4961':'#B7C4D6','#2B3B52':'#C1CDDC','#2C384B':'#D8E0EB',
    '#395570':'#B7C4D6','#365672':'#B7C4D6','#526C8B':'#869DB9','#465D78':'#98ACC5',
    '#FFFFFF':'#172638','#EDF2FA':'#172638','#E7EDF6':'#172638','#E5F0FA':'#172638',
    '#E7F0FC':'#172638','#EAF9F7':'#172638','#DCE7F5':'#26384D','#C9D8E8':'#394D66',
    '#A9B8CC':'#53657D','#A5B2C9':'#53657D','#B9CCDF':'#435A73','#8D9CB3':'#687E99',
    '#66738A':'#7B8798','#929BA9':'#68768A','#637B98':'#7185A0',
    '#644C20':'#FFF0CC','#54472B':'#FFF0CC','#775218':'#FFF0CC','#40354F':'#EEE5FA',
    '#1E5845':'#D9F1E5','#3D4962':'#DFE8F4','#303E55':'#E4ECF7',
    '#FFE5A3':'#754B00','#F1BB83':'#875000','#E9B875':'#875000','#F6D76B':'#765500',
    '#64DAC7':'#147D70','#65DCC7':'#147D70','#6CE2C9':'#147D70','#70DDEA':'#147C8B',
    '#102B2B':'#FFFFFF','#102334':'#FFFFFF','#294A4C':'#DAE8E5','#95AAA9':'#647572',
    '#36B4A2':'#10695E','#8DE8DA':'#198B7C',
}
COLOR_OPTIONS={'background','bg','foreground','fg','fieldbackground','insertbackground','insertcolor',
 'selectbackground','selectforeground','selectcolor','activebackground','activeforeground','disabledforeground',
 'highlightbackground','highlightcolor','troughcolor','arrowcolor','bordercolor','lightcolor','darkcolor',
 'indicatorbackground','indicatorforeground','focuscolor','fill','outline','activefill','activeoutline',
 'disabledfill','disabledoutline'}
_ORIGINAL={};_installed=False


def color(value,theme):
    if theme!='light' or not isinstance(value,str) or not re.fullmatch(r'#[\da-fA-F]{6}',value):return value
    key=value.upper()
    if key in LIGHT:return LIGHT[key]
    # Remaining custom chart colors retain their hue, with readable saturation on white.
    r,g,b=(int(key[i:i+2],16)/255 for i in (1,3,5))
    h,l,s=colorsys.rgb_to_hls(r,g,b)
    if l<.35:return '#DFE8F4'
    r,g,b=colorsys.hls_to_rgb(h,min(l,.38),max(s,.45))
    return '#'+''.join(f'{round(v*255):02X}' for v in (r,g,b))


def choose_font(requested,families):
    names={name.casefold():name for name in families}
    if requested.casefold() in names:return names[requested.casefold()]
    def normalize(value):
        return re.sub(r'[\s_-]+','',value.casefold()).replace('페이퍼로지','paperlogy').replace('프리텐다드','pretendard')
    wanted=normalize(requested)
    for family in families:
        if normalize(family)==wanted:return family
    # Older settings stored Windows full face names; Qt may expose the family alone.
    for family in sorted(families,key=len,reverse=True):
        base=normalize(family)
        if wanted.startswith(base) and re.fullmatch(r'\d*(thin|extralight|light|regular|medium|semibold|bold|extrabold|black)',wanted[len(base):]):return family
    if requested.casefold() in ('paperlogy','페이퍼로지'):
        candidates=sorted((name for name in families if 'paperlogy' in name.casefold() or '페이퍼로지' in name),key=lambda name:('regular' not in name.casefold(),'4 ' not in name,len(name)))
        if candidates:return candidates[0]
    return names.get('맑은 고딕',names.get('malgun gothic',names.get('noto sans cjk kr','TkDefaultFont')))


def controller(widget):
    try:return getattr(widget._root() if hasattr(widget,'_root') else widget.master._root(),'_appearance',None)
    except (AttributeError,tk.TclError):return None


class ChartFont(tuple):
    """Font specification that follows the independent chart preference."""


class NumericFont(tuple):
    """Font specification for numeric UI content, independent of charts."""


class Appearance:
    def __init__(self,root):
        self.root=root;self.theme='dark';self.requested=DEFAULT_FONT
        self.chart_requested='';self.chart_family=None;self.numeric_requested='';self.numeric_family=None
        self.family=choose_font(DEFAULT_FONT,tkfont.families(root));self.suspended=False;self.applied=False
        self.widgets=weakref.WeakKeyDictionary();self.items=weakref.WeakKeyDictionary();self.tags=weakref.WeakKeyDictionary();self.styles={};self.maps={}
    def options(self,options):
        out=dict(options)
        for key,value in options.items():
            if key in COLOR_OPTIONS:out[key]=color(value,self.theme)
        return out
    def update(self,theme,font,chart_font=None,numeric_font=None):
        settings=(theme,font,chart_font if chart_font is not None else self.chart_requested,numeric_font if numeric_font is not None else self.numeric_requested)
        if self.applied and getattr(self,'_last_settings',None)==settings:return
        self.theme=theme if theme in ('dark','light') else 'dark';self.requested=font
        self.family=choose_font(font,tkfont.families(self.root))
        if self.family=='TkDefaultFont':self.family=tk.application().font().family()
        if chart_font is not None:self.chart_requested=chart_font
        if numeric_font is not None:self.numeric_requested=numeric_font
        self.chart_family=choose_font(self.chart_requested,tkfont.families(self.root)) if self.chart_requested else self.family
        self.numeric_family=choose_font(self.numeric_requested,tkfont.families(self.root)) if self.numeric_requested else self.family
        self.applied=True
        self._last_settings=settings
        from ui_theme import qt_stylesheet
        tk.application().setStyleSheet(qt_stylesheet(self.theme))
        tk.application().setFont(tk.Font(font=(self.family,10)).q)
        # Styled native Qt controls can retain the family resolved before setFont().
        # Apply the family explicitly, retaining each control's size and weight.
        for native in tk.application().allWidgets():
            if native is self.root._q or self.root._q.isAncestorOf(native):
                updated=tk.G.QFont(native.font());updated.setFamily(self.family);native.setFont(updated)
        for widget in list(tk._registry.values()):
            if not widget.winfo_exists():continue
            if isinstance(widget,tk.Window) and widget._q.isWindow():
                from ui_theme import dark_titlebar
                dark_titlebar(widget)
            raw={k:v for k,v in widget._options.items() if k in COLOR_OPTIONS}
            if raw:widget.configure(**raw)
            else:widget._apply_label_font()
            if isinstance(widget,tk.Canvas):
                for identity in list(widget._items):widget._apply_item(identity)
                widget.event_generate('<Configure>')
            if isinstance(widget,ttk.Treeview):widget.refresh_numbers()
            widget.event_generate('<<ThemeChanged>>')


def install():pass

def initialize(root):
    if not hasattr(root._root(),'_appearance'):root._root()._appearance=Appearance(root._root())
    return root._root()._appearance


def set_appearance(root,theme,font,chart_font=None,numeric_font=None):
    appearance=initialize(root)
    appearance.update(theme,font,chart_font,numeric_font)
    return appearance.family
