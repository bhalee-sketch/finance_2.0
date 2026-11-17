"""Compact, visibly separated detail rows with bounded scrolling."""
import qt_ui as tk


def configure_detail_table(tree):
    tree._cell_grid=True
    tree._q.setShowGrid(True)
    tree._q.setStyleSheet('QTableView {gridline-color:#C8BFD7;alternate-background-color:rgba(149,116,210,22);}')
    tree._q.setVerticalScrollMode(tk.W.QAbstractItemView.ScrollMode.ScrollPerPixel)
    def clamp(*args):
        if not tree.winfo_exists():return
        bar=tree._q.verticalScrollBar()
        maximum=max(0,tree._q.verticalHeader().length()-tree._q.viewport().height())
        if bar.maximum()>maximum:bar.setMaximum(maximum)
    tree._q.verticalScrollBar().rangeChanged.connect(clamp)
    tree.bind('<Configure>',lambda event:tree.after_idle(clamp),add='+')
    tree.model.modelReset.connect(lambda:tree.after_idle(clamp))
    tree.after_idle(clamp)
