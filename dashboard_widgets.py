"""Small native Qt views shared by the financial dashboard and loan workspace."""
from concurrent.futures import Future
from threading import Thread

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from dashboard_finance import won


def background(owner, read, done, failed):
    """Only deliver a completed snapshot while its owning widget still exists."""
    future = Future()
    def work():
        try:
            future.set_result(read())
        except Exception as exc:
            future.set_exception(exc)
    timer = C.QTimer(owner)
    def receive():
        if not future.done():
            return
        timer.stop()
        timer.deleteLater()
        try:
            value = future.result()
            done(value)
        except Exception as exc:
            failed(exc)
    timer.timeout.connect(receive)
    timer.start(35)
    Thread(target=work,daemon=True).start()


class DataTable(W.QTableWidget):
    def __init__(self):
        super().__init__()
        self.verticalHeader().hide()
        self.setEditTriggers(W.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setMinimumSize(0,64)
        self.setHorizontalScrollMode(W.QAbstractItemView.ScrollMode.ScrollPerPixel)

    def populate(self,headers,rows):
        self.clear()
        self.setColumnCount(len(headers))
        self.setRowCount(len(rows))
        self.setHorizontalHeaderLabels(headers)
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                text = str(value if value is not None else '미등록')
                item = W.QTableWidgetItem(text)
                item.setToolTip(text)
                if text.endswith('원') or text.replace(',','').lstrip('-').isdigit():
                    item.setTextAlignment(C.Qt.AlignmentFlag.AlignRight|C.Qt.AlignmentFlag.AlignVCenter)
                self.setItem(i,j,item)
        self.resizeColumnsToContents()
        self.resizeRowsToContents()


class BalanceTable(DataTable):
    """Keep the four columns readable and share extra width between both sides."""
    def __init__(self):
        super().__init__()
        self.base_widths = []
        self.verticalHeader().setObjectName('DashboardBalanceRows')

    def fit(self):
        self.resizeColumnsToContents()
        self.base_widths = [self.columnWidth(col) for col in range(self.columnCount())]
        self.spread_columns()

    def spread_columns(self):
        if not self.base_widths:
            return
        extra = max(0, self.viewport().width() - sum(self.base_widths))
        for col, width in enumerate(self.base_widths):
            self.setColumnWidth(col, width + extra // 4 + int(col < extra % 4))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.spread_columns()


class Trend(W.QWidget):
    colors = ('#364586','#9676C5')

    def __init__(self,labels,line=False):
        super().__init__()
        self.labels = labels
        self.line = line
        self.rows = []
        self.regions = []
        self.empty_text = '조회 중…'
        self.setMinimumSize(150,150)
        self.setSizePolicy(W.QSizePolicy.Policy.Expanding,W.QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_rows(self,rows,empty_text='자료 없음'):
        self.rows = rows
        self.empty_text = empty_text
        self.regions.clear()
        self.update()

    def paintEvent(self,event):
        p = G.QPainter(self)
        p.setRenderHint(G.QPainter.RenderHint.Antialiasing)
        text = self.palette().color(G.QPalette.ColorRole.Text)
        metrics = p.fontMetrics()
        h = metrics.height()
        self.regions = []
        if not any(v is not None for _, values in self.rows for v in values):
            p.drawText(self.rect(),C.Qt.AlignmentFlag.AlignCenter,self.empty_text)
            return
        values = [float(v/100_000_000) for _,vals in self.rows for v in vals if v is not None]
        high = max([0,*values])
        low = min([0,*values])
        if high==low:
            high = low+1
        labels = [f'{v:,.0f}' if high-low>=2 else f'{v:,.1f}' for v in (low,(low+high)/2,high)]
        left = max(metrics.horizontalAdvance(s) for s in labels)+7
        top = h
        bottom = self.height()-h*2-13
        step = (self.width()-left-5)/len(self.rows)
        def ypos(val):
            return bottom-(val-low)/(high-low)*(bottom-top)
        for i,label in enumerate(labels):
            y = bottom-(bottom-top)*i/2
            p.setPen(G.QColor('#D9D6E4'))
            p.drawLine(C.QPointF(left,y),C.QPointF(self.width()-2,y))
            p.setPen(text)
            p.drawText(C.QRectF(0,y-h/2,left-4,h),C.Qt.AlignmentFlag.AlignRight|C.Qt.AlignmentFlag.AlignVCenter,label)
        prev = [None]*len(self.labels)
        for i,(year,vals) in enumerate(self.rows):
            x = left+(i+.5)*step
            rect = C.QRectF(x-step/2,top,step,bottom-top+h+4)
            tip = [f'{year}회계연도']
            for j,(name,v) in enumerate(zip(self.labels,vals)):
                tip.append(f'{name}  {won(v)}')
                if v is None:
                    prev[j] = None
                    continue
                y = ypos(float(v/100_000_000))
                color = G.QColor(self.colors[j])
                p.setBrush(color)
                p.setPen(G.QPen(color,2))
                point = C.QPointF(x,y)
                if self.line:
                    if prev[j] is not None:
                        p.drawLine(prev[j],point)
                    p.drawEllipse(point,3,3)
                else:
                    p.fillRect(C.QRectF(x-step*.27,min(y,ypos(0)),step*.54,max(2,abs(y-ypos(0)))),color)
                prev[j] = point
            self.regions.append((rect,'\n'.join(tip)))
            p.setPen(text)
            p.drawText(C.QRectF(x-step/2,bottom+4,step,h+2),C.Qt.AlignmentFlag.AlignCenter,str(year))
        legend = '   '.join(self.labels)
        x = max(2,(self.width()-metrics.horizontalAdvance(legend)-24*len(self.labels))/2)
        for j,label in enumerate(self.labels):
            p.fillRect(C.QRectF(x,self.height()-h/2-5,9,4),G.QColor(self.colors[j]))
            p.setPen(text)
            p.drawText(C.QPointF(x+13,self.height()-4),label)
            x += metrics.horizontalAdvance(label)+24

    def event(self,event):
        if event.type()==C.QEvent.Type.ToolTip:
            for rect,tip in self.regions:
                if rect.contains(event.position() if hasattr(event,'position') else event.pos()):
                    W.QToolTip.showText(event.globalPos(),tip,self)
                    return True
            W.QToolTip.hideText()
        return super().event(event)
