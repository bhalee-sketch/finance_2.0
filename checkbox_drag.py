"""Paint a consistent checked state across a table's checkbox column."""
import qt_ui as tk


class CheckboxDrag(tk.C.QObject):
    def __init__(self,view,column=0):
        super().__init__(view)
        self.view=view;self.column=column;self.anchor=None;self.checked=False;self.position=None
        self.timer=tk.C.QTimer(self);self.timer.setInterval(60);self.timer.timeout.connect(self.scroll)
        view.viewport().setMouseTracking(True)
        tk.application().installEventFilter(self)

    def checkbox(self,row):
        index=self.view.model().index(row,self.column)
        holder=self.view.indexWidget(index)
        return holder.findChild(tk.W.QCheckBox) if holder else None

    def paint_to(self,row):
        for index in range(min(self.anchor,row),max(self.anchor,row)+1):
            check=self.checkbox(index)
            if check and check.isEnabled():check.setChecked(self.checked)

    def stop(self):
        self.anchor=None;self.position=None;self.timer.stop()

    def move(self,position):
        self.position=position
        viewport=self.view.viewport();point=viewport.mapFromGlobal(position)
        if self.view.columnAt(point.x())!=self.column:return
        y=max(0,min(point.y(),viewport.height()-1))
        row=self.view.rowAt(y)
        count=self.view.model().rowCount()
        if row<0 and count and y>=self.view.rowViewportPosition(count-1):row=count-1
        if row>=0:self.paint_to(row)

    def scroll(self):
        if self.anchor is None or not self.view.isVisible():self.stop();return
        viewport=self.view.viewport();point=viewport.mapFromGlobal(self.position)
        if self.view.columnAt(point.x())!=self.column:return
        delta=-1 if point.y()<18 else 1 if point.y()>viewport.height()-18 else 0
        if delta:
            bar=self.view.verticalScrollBar();bar.setValue(bar.value()+delta*self.view.verticalHeader().defaultSectionSize())
            self.move(self.position)

    def eventFilter(self,obj,event):
        kind=event.type()
        if kind in (tk.C.QEvent.Type.Hide,tk.C.QEvent.Type.WindowDeactivate) and obj is self.view:self.stop()
        if kind==tk.C.QEvent.Type.MouseButtonPress and event.button()==tk.C.Qt.MouseButton.LeftButton:
            viewport=self.view.viewport()
            if not isinstance(obj,tk.W.QWidget) or not (obj is viewport or viewport.isAncestorOf(obj)):return False
            position=event.globalPosition().toPoint();point=viewport.mapFromGlobal(position)
            index=self.view.indexAt(point)
            if not index.isValid() or index.column()!=self.column:return False
            check=self.checkbox(index.row())
            if not check or not check.isEnabled():return False
            self.anchor=index.row();self.checked=not check.isChecked();self.position=position
            check.setChecked(self.checked);self.timer.start();return True
        if self.anchor is not None:
            if kind==tk.C.QEvent.Type.MouseMove:
                if not event.buttons()&tk.C.Qt.MouseButton.LeftButton:self.stop();return False
                self.move(event.globalPosition().toPoint());return True
            if kind==tk.C.QEvent.Type.MouseButtonRelease and event.button()==tk.C.Qt.MouseButton.LeftButton:
                self.move(event.globalPosition().toPoint());self.stop();return True
        return False
