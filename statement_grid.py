"""Financial statement cells share the direct cell-font renderer."""
from numeric_tree import NumericTreeview
from qt_ui import C,G,W

ROW_COLORS={'gwan':'#D7E7F5','hang':'#EAE3F6','mok':'#FFFFFF','total_green':'#D9EFE6'}
SELECTION_COLOR='#E5E7EB'
CURRENT_CELL_COLOR='#64748B'


class StatementHeader(W.QHeaderView):
    def paintSection(self,painter,rect,index):
        if not rect.isValid():return
        option=W.QStyleOptionHeader();self.initStyleOptionForIndex(option,index)
        text=option.text;option.text='';option.rect=rect
        painter.save();self.style().drawControl(W.QStyle.ControlElement.CE_Header,option,painter,self)
        painter.setPen(self.palette().color(G.QPalette.ColorRole.Text))
        painter.drawText(rect.adjusted(4,4,-18,-4),C.Qt.AlignmentFlag.AlignCenter|C.Qt.TextFlag.TextWordWrap|C.Qt.TextFlag.TextWrapAnywhere,text)
        painter.restore()

    def wrapped_height(self):
        metrics=G.QFontMetrics(self.font());height=36
        for col in range(self.count()):
            text=str(self.model().headerData(col,C.Qt.Orientation.Horizontal) or '')
            rect=metrics.boundingRect(C.QRect(0,0,max(1,self.sectionSize(col)-22),10000),C.Qt.TextFlag.TextWordWrap|C.Qt.TextFlag.TextWrapAnywhere,text)
            height=max(height,rect.height()+12)
        return height


class StatementCellDelegate(W.QStyledItemDelegate):
    def paint(self,painter,option,index):
        styled=W.QStyleOptionViewItem(option)
        self.initStyleOption(styled,index)
        styled.state &= ~W.QStyle.StateFlag.State_HasFocus
        view=self.parent()
        if view.wordWrap():
            text=styled.text;styled.text=''
            painter.save();painter.setClipRect(option.rect,C.Qt.ClipOperation.IntersectClip)
            view.style().drawControl(W.QStyle.ControlElement.CE_ItemViewItem,styled,painter,view)
            painter.setFont(styled.font);painter.setPen(G.QColor('#172638'))
            painter.drawText(option.rect.adjusted(5,3,-5,-3),styled.displayAlignment|C.Qt.TextFlag.TextWordWrap|C.Qt.TextFlag.TextWrapAnywhere,text)
            painter.restore()
        else:super().paint(painter,styled,index)
        if index==view.currentIndex() and view.selectionModel().isSelected(index):
            painter.save();painter.setPen(G.QPen(G.QColor(CURRENT_CELL_COLOR),1))
            painter.setBrush(C.Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(0,0,-1,-1));painter.restore()

    def sizeHint(self,option,index):
        view=self.parent()
        if not view.wordWrap():return super().sizeHint(option,index)
        styled=W.QStyleOptionViewItem(option);self.initStyleOption(styled,index)
        width=max(1,view.columnWidth(index.column())-11)
        rect=G.QFontMetrics(styled.font).boundingRect(C.QRect(0,0,width,100000),C.Qt.TextFlag.TextWordWrap|C.Qt.TextFlag.TextWrapAnywhere,styled.text)
        return C.QSize(width+11,max(view.verticalHeader().defaultSectionSize(),rect.height()+7))


class StatementGrid(NumericTreeview):
    def __init__(self,parent,**kwargs):
        super().__init__(parent,**kwargs)
        self._cell_grid=True
        self._q.setAlternatingRowColors(False)
        self._q.setStyleSheet(f'QTableView {{background:#FFFFFF; color:#172638; selection-background-color:{SELECTION_COLOR}; selection-color:#172638;}} QTableView::item:selected {{background:{SELECTION_COLOR}; color:#172638;}}')
        self._q.setItemDelegate(StatementCellDelegate(self._q))

    def _color(self,value):
        if isinstance(value,str) and value.upper() in {*ROW_COLORS.values(),'#172638',SELECTION_COLOR,CURRENT_CELL_COLOR}:return value
        return super()._color(value)

    def fit_to_viewport(self,preferred,subject_column):
        """Keep every column visible, with a stable subject width and wrapped cells."""
        if not preferred:return
        self._fit_request=(dict(preferred),subject_column)
        if not getattr(self,'_fit_header_installed',False):
            old=self._q.horizontalHeader();indicator=old.sortIndicatorSection();order=old.sortIndicatorOrder()
            sort_column=self.proxy.sortColumn();sort_order=self.proxy.sortOrder()
            header=StatementHeader(C.Qt.Orientation.Horizontal,self._q)
            self._q.setHorizontalHeader(header);header.setSortIndicator(indicator,order)
            self.proxy.sort(sort_column,sort_order);header.show()
            header.setSectionsClickable(True);header.sectionClicked.connect(self._header_clicked)
            header.setMinimumSectionSize(1);header.setSectionResizeMode(W.QHeaderView.ResizeMode.Fixed)
            self._q.setWordWrap(True);self._q.setTextElideMode(C.Qt.TextElideMode.ElideNone)
            self._q.setShowGrid(True)
            self._q.setHorizontalScrollBarPolicy(C.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._fit_header_installed=True
            def sorted_rows(*args):
                self._fit_signature=None
                self.after_idle(lambda:self.fit_to_viewport(*self._fit_request))
            self.proxy.layoutChanged.connect(sorted_rows)
        available=max(1,self._q.viewport().width());count=len(preferred)
        subject=min(320,int(available*.4)) if count>1 else available
        others=[i for i in range(count) if i!=subject_column]
        total=sum(list(preferred.values())[i] for i in others) or 1
        widths=[0]*count;widths[subject_column]=subject;remaining=available-subject
        for i in others:widths[i]=max(1,int(remaining*list(preferred.values())[i]/total))
        if others:widths[others[-1]]+=available-sum(widths)
        appearance=getattr(self._root(),'_appearance',None)
        fonts=(getattr(appearance,'family',''),getattr(appearance,'numeric_family',''))
        signature=(tuple(widths),self._q.font().toString(),fonts,tuple(self.model.rows))
        if getattr(self,'_fit_signature',None)==signature:return
        self._fit_signature=signature
        for index,(col,width) in enumerate(zip(preferred,widths)):
            self._column_options.setdefault(col,{})['width']=width;self._q.setColumnWidth(index,width)
        self._q.horizontalHeader().setFixedHeight(self._q.horizontalHeader().wrapped_height())
        if getattr(self,'_row_wrap_job',None) is not None:self.after_cancel(self._row_wrap_job)
        row=0
        def resize_chunk():
            nonlocal row
            self._row_wrap_job=None
            if not self.winfo_exists():return
            end=min(row+40,self.proxy.rowCount())
            while row<end:self._q.resizeRowToContents(row);row+=1
            if row<self.proxy.rowCount():self._row_wrap_job=self.after(1,resize_chunk)
        self._row_wrap_job=self.after(1,resize_chunk)

    def refresh_grid(self,event=None):
        self.refresh_numbers(event)
