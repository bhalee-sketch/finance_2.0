"""Application-owned record table for appendix data, following global appearance."""
from datetime import date,datetime,time
import qt_ui as tk


def display_value(value):
    if value is None:return ''
    if isinstance(value,bool):return str(value)
    if isinstance(value,(int,float)):
        return f'{value:,}' if isinstance(value,int) else f'{value:,.2f}'.rstrip('0').rstrip('.')
    if isinstance(value,(date,datetime,time)):return value.isoformat()
    return ' '.join(str(value).split())


class AppendixModel(tk.C.QAbstractTableModel):
    def __init__(self,window,view):
        super().__init__(view);self.window=window;self.view=view;self.sheet={'headers':[],'records':[]}
    def replace(self,sheet):
        self.beginResetModel();self.sheet=sheet;self.span_labels={(row,start):label for row,start,span,label in sheet.get('spans',[])};self.endResetModel()
    def rowCount(self,parent=tk.C.QModelIndex()):return 0 if parent.isValid() else len(self.sheet['records'])
    def columnCount(self,parent=tk.C.QModelIndex()):return 0 if parent.isValid() else len(self.sheet['headers'])
    def headerData(self,section,orientation,role=tk.C.Qt.ItemDataRole.DisplayRole):
        if role!=tk.C.Qt.ItemDataRole.DisplayRole:return None
        return self.sheet['headers'][section] if orientation==tk.C.Qt.Orientation.Horizontal else str(section+1)
    def data(self,index,role=tk.C.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        value=self.sheet['records'][index.row()]['values'][index.column()]
        numeric=isinstance(value,(int,float)) and not isinstance(value,bool)
        total=self.sheet.get('totals',{}).get(index.row())
        if role==tk.C.Qt.ItemDataRole.BackgroundRole and total:
            from appearance import controller
            appearance=controller(self.window);dark=appearance and appearance.theme=='dark'
            return tk.G.QColor(('#38566B' if total=='total' else '#46395B') if dark else ('#D6E8F5' if total=='total' else '#EAE0F5'))
        if role==tk.C.Qt.ItemDataRole.ForegroundRole and total:
            from appearance import controller
            appearance=controller(self.window)
            return tk.G.QColor('#F4F0FA' if appearance and appearance.theme=='dark' else '#302840')
        if role==tk.C.Qt.ItemDataRole.DisplayRole:
            label=getattr(self,'span_labels',{}).get((index.row(),index.column()),index.column())
            return display_value(self.sheet['records'][index.row()]['values'][label])
        if role==tk.C.Qt.ItemDataRole.ToolTipRole:return '' if value is None else str(value)
        if role==tk.C.Qt.ItemDataRole.UserRole:return value
        if role==tk.C.Qt.ItemDataRole.TextAlignmentRole:
            return int((tk.C.Qt.AlignmentFlag.AlignRight if numeric else tk.C.Qt.AlignmentFlag.AlignLeft)|tk.C.Qt.AlignmentFlag.AlignVCenter)
        if role==tk.C.Qt.ItemDataRole.FontRole:
            from appearance import controller
            appearance=controller(self.window);font=tk.G.QFont(self.view.font())
            if appearance:font.setFamily((appearance.numeric_family or appearance.family) if numeric else appearance.family)
            if total:font.setBold(True)
            if appearance and getattr(appearance,'text_sizes',None):font.setPointSizeF(appearance.text_sizes['data'])
            return tk.readable_font(font)
        return None
