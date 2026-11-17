"""Antialiased chart geometry on the Qt graphics surface; native text and events remain.

Only the display layer is supersampled. Coordinates, values, scales and gaps are
unchanged, and straight segments are never interpolated into curves.
"""
from functools import wraps
import math
import qt_ui as tk
from qt_ui import Canvas as NativeCanvas
from PIL import Image, ImageDraw
from qt_ui import ImageTk
from appearance import ChartFont, controller, color


def raster_shape(kind,coords,options,theme='dark',scale=3):
    width=float(options.get('width',1));pad=math.ceil(width/2)+2
    xs=coords[::2];ys=coords[1::2]
    left=math.floor(min(xs))-pad;top=math.floor(min(ys))-pad
    size=(max(1,math.ceil(max(xs))-left+pad),max(1,math.ceil(max(ys))-top+pad))
    image=Image.new('RGBA',(size[0]*scale,size[1]*scale))
    draw=ImageDraw.Draw(image)
    points=[((x-left)*scale,(y-top)*scale) for x,y in zip(xs,ys)]
    fill=color(options.get('fill',''),theme) or None
    outline=color(options.get('outline',''),theme) or None
    stroke=max(1,round(width*scale))
    if kind=='line':
        draw.line(points,fill=fill,width=stroke,joint='curve')
        if options.get('capstyle')=='round':
            r=stroke/2
            for x,y in (points[0],points[-1]):draw.ellipse((x-r,y-r,x+r,y+r),fill=fill)
    elif kind=='polygon':
        draw.polygon(points,fill=fill)
        if outline:draw.line(points+[points[0]],fill=outline,width=stroke,joint='curve')
    else:draw.ellipse((*points[0],*points[1]),fill=fill,outline=outline,width=stroke)
    return image.resize(size,Image.Resampling.LANCZOS),(left,top)


class ChartSurface:
    def __init__(self,canvas):self.canvas=canvas
    def __getattr__(self,name):return getattr(self.canvas,name)
    def delete(self,*tags):
        self.canvas.delete(*tags)
        if 'all' in tags:
            self.canvas._chart_images={}
            for event,binding in getattr(self.canvas,'_chart_hover_bindings',[]):self.canvas.unbind(event,binding)
            self.canvas._chart_hover_bindings=[]
        else:
            images=getattr(self.canvas,'_chart_images',{})
            for item in list(images):
                if not self.canvas.type(item):images.pop(item,None)
    def create_text(self,*args,**kwargs):
        kwargs['font']=ChartFont(kwargs.get('font',('맑은 고딕',10)))
        return self.canvas.create_text(*args,**kwargs)
    def shape(self,kind,args,kwargs):
        coords=list(tk._flatten(args));appearance=controller(self.canvas)
        bitmap,origin=raster_shape(kind,coords,kwargs,appearance.theme if appearance else 'dark')
        photo=ImageTk.PhotoImage(bitmap,master=self.canvas)
        # Decorative lines must not intercept the existing point/bar hover events.
        item=self.canvas.create_image(*origin,image=photo,anchor='nw',tags=kwargs.get('tags',()),state='normal' if kind=='oval' else 'disabled')
        if not hasattr(self.canvas,'_chart_images'):self.canvas._chart_images={}
        self.canvas._chart_images[item]=photo
        return item
    def create_line(self,*args,**kwargs):return self.shape('line',args,kwargs)
    def create_polygon(self,*args,**kwargs):return self.shape('polygon',args,kwargs)
    def create_oval(self,*args,**kwargs):return self.shape('oval',args,kwargs)


def polished_chart(draw):
    @wraps(draw)
    def render(canvas,*args,**kwargs):
        return draw(ChartSurface(canvas) if isinstance(canvas,NativeCanvas) else canvas,*args,**kwargs)
    return render
