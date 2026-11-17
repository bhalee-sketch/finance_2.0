"""재무제표 Excel 읽기: 공통 구형 XLS 인코딩/행 수 보완 사용."""
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from verifier import open_legacy_workbook


def sheet_names(path):
    if Path(path).suffix.lower()=='.xls':
        w=open_legacy_workbook(Path(path))
        try:return w.sheet_names()
        finally:w.release_resources()
    w=load_workbook(path,read_only=True,data_only=True)
    try:return w.sheetnames
    finally:w.close()


def read_frame(path,sheet_name=0):
    if Path(path).suffix.lower()=='.xls':
        w=open_legacy_workbook(Path(path))
        try:
            s=w.sheet_by_index(sheet_name) if isinstance(sheet_name,int) else w.sheet_by_name(sheet_name)
            return pd.DataFrame([s.row_values(i) for i in range(s.nrows)])
        finally:w.release_resources()
    return pd.read_excel(path,sheet_name=sheet_name,header=None,engine='openpyxl')
