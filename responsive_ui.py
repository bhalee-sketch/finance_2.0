"""Wrapping rows for dense toolbars, preserving existing widget callbacks."""
import qt_ui as q


class WrappingLayout(q.PackLayout):
    def __init__(self, parent, uniform_height=False):
        self.uniform_height = uniform_height
        super().__init__(parent)

    def _arrange(self,width,rect=None):
        x=y=height=0;gap=8
        items = [(item, item.sizeHint(), options) for item, options in self.entries if not item.widget().isHidden()]
        row_height = max((size.height() for _, size, _ in items), default=0) if self.uniform_height else 0
        for item,size,options in items:
            w=min(max(0,width),size.width());h=row_height or size.height()
            if x and x+w>width:x=0;y+=height+gap;height=0
            if item is items[-1][0] and options.get('side') == 'right':
                x = width - w
            if rect is not None:item.setGeometry(q.C.QRect(rect.x()+x,rect.y()+y,w,h))
            x+=w+gap;height=max(height,h)
        return y+height
    def hasHeightForWidth(self):return False
    def heightForWidth(self,width):return self._arrange(width)
    def minimumSize(self):
        sizes=[item.minimumSize() for item,_ in self.entries if not item.widget().isHidden()]
        return q.C.QSize(max((s.width() for s in sizes),default=0),max((s.height() for s in sizes),default=0))
    def sizeHint(self):
        size=self.minimumSize()
        return q.C.QSize(size.width(),getattr(self,'_last_height',size.height()))
    def setGeometry(self,rect):
        q.W.QLayout.setGeometry(self,rect);height=self._arrange(rect.width(),rect)
        if getattr(self,'_last_height',None)!=height:
            self._last_height=height
            self.parentWidget().setFixedHeight(height)
            parent=self.parentWidget().parentWidget()
            while parent is not None:
                if parent.layout():parent.layout().invalidate()
                parent.updateGeometry();parent=parent.parentWidget()


def wrapping_row(parent, *, uniform_height=False):
    frame=q.Frame(parent);WrappingLayout(frame._q, uniform_height)
    return frame
