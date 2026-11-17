"""Qt model/view tables with independent per-cell numeric fonts."""
from functools import lru_cache
import re
import qt_ui as tk
from qt_ui import ttk, font as tkfont


def numeric_text(value):
    return bool(re.fullmatch(r'\s*[+−-]?(?:\d[\d,]*(?:\.\d+)?|\(\d[\d,]*(?:\.\d+)?\))\s*(?:%|원|건|명|백만원)?\s*',str(value)))


def numeric_cell(heading,value):
    heading=str(heading).casefold()
    return not any(word in heading for word in ('코드','일자','날짜','번호','계좌','연도','원본행','순번','row_id','id','date','code','account','number')) and numeric_text(value)


class NumericTreeview(ttk.Treeview):
    """Qt model/view table; numeric fonts are selected per cell by TableModel."""
    pass
