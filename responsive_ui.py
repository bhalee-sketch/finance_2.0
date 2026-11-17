"""Wrapping rows for dense toolbars, preserving existing widget callbacks."""
import qt_ui as q


class WrappingLayout(q.PackLayout):
    def _arrange(self,width,rect=None):
        x=y=height=0;gap=8
        for item,options in self.entries:
            if item.widget().isHidden():continue
            size=item.sizeHint();w=min(max(0,width),size.width());h=size.height()
            if x and x+w>width:x=0;y+=height+gap;height=0
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


def wrapping_row(parent):
    frame=q.Frame(parent);WrappingLayout(frame._q)
    return frame
