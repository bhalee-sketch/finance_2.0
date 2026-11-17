"""Small launcher-only presentation widgets, with keyboard and hover feedback."""
import qt_ui as tk
from PIL import Image,ImageDraw
from qt_ui import ImageTk
from appearance import controller,color


def settings_icon(button,size=18,kind='settings'):
    """A font-independent eight-tooth gear with a clear central opening."""
    import math
    def redraw(event=None):
        scale=4;edge=size*scale;center=edge/2
        appearance=controller(button);theme=appearance.theme if appearance else 'dark'
        ink=color('#93C5FD',theme)
        image=Image.new('RGBA',(edge,edge));draw=ImageDraw.Draw(image)
        points=[]
        for tooth in range(8):
            for offset,radius in ((-.5,.35),(-.27,.35),(-.23,.47),(.23,.47),(.27,.35),(.5,.35)):
                angle=(tooth+offset)*math.tau/8
                points.append((center+math.cos(angle)*edge*radius,center+math.sin(angle)*edge*radius))
        draw.polygon(points,fill=ink)
        hole=edge*.17
        draw.ellipse((center-hole,center-hole,center+hole,center+hole),fill=(0,0,0,0))
        if kind!='settings':
            image=Image.new('RGBA',(edge,edge));draw=ImageDraw.Draw(image)
            stroke=max(4,round(edge*.09));lo=edge*.2;hi=edge*.8
            if kind=='close':
                draw.line((lo,lo,hi,hi),fill=ink,width=stroke)
                draw.line((lo,hi,hi,lo),fill=ink,width=stroke)
            elif kind=='floating':
                draw.rounded_rectangle((edge*.09,edge*.16,edge*.91,edge*.84),radius=edge*.06,outline=ink,width=stroke)
                draw.rounded_rectangle((edge*.47,edge*.47,edge*.82,edge*.74),radius=edge*.03,fill=ink)
        button._gear_image=ImageTk.PhotoImage(image.resize((size,size),Image.Resampling.LANCZOS),master=button)
        button.configure(image=button._gear_image,text='')
    button.bind('<<ThemeChanged>>',redraw,add='+')
    redraw()


def tooltip(widget,text):
    state={'job':None,'window':None}
    def hide(event=None):
        if state['job'] is not None:
            widget.after_cancel(state['job']);state['job']=None
        if state['window'] is not None:
            state['window'].destroy();state['window']=None
    def show():
        state['job']=None
        if not widget.winfo_exists():return
        window=tk.Toplevel(widget);state['window']=window
        window.overrideredirect(True);window.attributes('-topmost',True)
        tk.Label(window,text=text,bg='#172231',fg='#E2E8F0',padx=8,pady=4).pack()
        window.geometry(f'+{widget.winfo_rootx()}+{widget.winfo_rooty()+widget.winfo_height()+4}')
    def enter(event):state['job']=widget.after(450,show)
    widget.bind('<Enter>',enter,add='+');widget.bind('<Leave>',hide,add='+')
    widget.bind('<ButtonPress>',hide,add='+');widget.bind('<Destroy>',hide,add='+')


class MenuButton(tk.Button):
    """Native Qt navigation button with keyboard focus and DPI-aware sizing."""
    def __init__(self,master,text,command,selected=False,child=False,factor=1):
        self.command=command;self.caption=text;self.selected=selected;self.child=child
        self.hover=False;self.pressed=False;self.factor=factor
        super().__init__(master,text=text,command=command,cursor='hand2')
        self._q.setMinimumHeight(round((34 if child else 42)*factor))
        self._q.setSizePolicy(tk.W.QSizePolicy.Policy.Expanding,tk.W.QSizePolicy.Policy.Fixed)
        self._q.setProperty('navigation',True);self._q.setProperty('selected',selected)
        self._q.setFont(tk.Font(font=('맑은 고딕',max(8,round(10*factor)),'normal' if child else 'bold')).q)
        self.redraw()
    def state(self,**values):
        for key,value in values.items():setattr(self,key,value)
        self.redraw()
    def release(self,event):
        if 0<=event.x<self.winfo_width() and 0<=event.y<self.winfo_height():self.command()
    def redraw(self,event=None):
        appearance=controller(self);theme=appearance.theme if appearance else 'dark'
        fill=color('#223653' if self.selected else '#172231',theme)
        fg=color('#E2E8F0',theme);accent=color('#93C5FD',theme)
        self._q.setStyleSheet(f'QPushButton {{ text-align:left; background:{fill}; color:{fg}; padding:7px {22 if self.child else 12}px; border:1px solid transparent; border-radius:6px; }} QPushButton:hover,QPushButton:focus {{ border-color:{accent}; }}')
        self._q.setText(self.caption+('  ⌃' if self.selected else '  ⌄') if not self.child else self.caption)
