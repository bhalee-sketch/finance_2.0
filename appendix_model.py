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
        self.beginResetModel();self.sheet=sheet;self.endResetModel()
    def rowCount(self,parent=tk.C.QModelIndex()):return 0 if parent.isValid() else len(self.sheet['records'])
    def columnCount(self,parent=tk.C.QModelIndex()):return 0 if parent.isValid() else len(self.sheet['headers'])
    def headerData(self,section,orientation,role=tk.C.Qt.ItemDataRole.DisplayRole):
        if role!=tk.C.Qt.ItemDataRole.DisplayRole:return None
        return self.sheet['headers'][section] if orientation==tk.C.Qt.Orientation.Horizontal else str(section+1)
    def data(self,index,role=tk.C.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        value=self.sheet['records'][index.row()]['values'][index.column()]
        numeric=isinstance(value,(int,float)) and not isinstance(value,bool)
        if role==tk.C.Qt.ItemDataRole.DisplayRole:return display_value(value)
        if role==tk.C.Qt.ItemDataRole.ToolTipRole:return '' if value is None else str(value)
        if role==tk.C.Qt.ItemDataRole.UserRole:return value
        if role==tk.C.Qt.ItemDataRole.TextAlignmentRole:
            return int((tk.C.Qt.AlignmentFlag.AlignRight if numeric else tk.C.Qt.AlignmentFlag.AlignLeft)|tk.C.Qt.AlignmentFlag.AlignVCenter)
        if role==tk.C.Qt.ItemDataRole.FontRole:
            from appearance import controller
            appearance=controller(self.window);font=tk.G.QFont(self.view.font())
            if appearance:font.setFamily((appearance.numeric_family or appearance.family) if numeric else appearance.family)
            return tk.readable_font(font)
        return None
