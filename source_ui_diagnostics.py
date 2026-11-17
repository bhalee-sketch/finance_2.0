"""Source-test-only GUI watchdog; captures stacks when the event loop stalls."""
import faulthandler
from datetime import datetime
from pathlib import Path
from PySide6 import QtCore as C


class GuiWatchdog(C.QObject):
    def __init__(self,app,path,timeout=8):
        super().__init__(app)
        self.app=app;self.timeout=timeout;self.closed=False
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.log=path.open('a',encoding='utf-8',buffering=1)
        self.log.write('\nGUI session '+datetime.now().isoformat()+'\n')
        self.timer=C.QTimer(self);self.timer.setInterval(1000)
        self.timer.timeout.connect(self.heartbeat)
        app.installEventFilter(self);app.aboutToQuit.connect(self.close)
        self.heartbeat();self.timer.start()

    def heartbeat(self):
        if not self.closed:
            faulthandler.dump_traceback_later(self.timeout,file=self.log,repeat=False)

    def eventFilter(self,obj,event):
        if not self.closed and event.type()==C.QEvent.Type.MouseButtonPress:
            # No input values or financial data are written.
            self.log.write(f'{datetime.now().isoformat()} click {obj.metaObject().className()} {obj.objectName()}\n')
        return False

    def close(self):
        if self.closed:return
        self.closed=True;self.timer.stop();self.app.removeEventFilter(self)
        faulthandler.cancel_dump_traceback_later();self.log.close()
