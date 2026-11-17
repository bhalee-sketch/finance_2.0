"""사용자 샘플에서 데이터 없이 추출한 차입금 보고서 서식."""
from copy import copy
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

STYLE_ATTRS=('font','fill','border','alignment','number_format','protection')


def copy_cell_style(source,target):
    for attr in STYLE_ATTRS:setattr(target,attr,copy(getattr(source,attr)))


def apply_loan_sample(wb):
    template=load_workbook(Path(__file__).parent/'templates/loan_report_style.xlsx')
    try:
        for ws in wb:
            name='선택연도_분기별상환예정' if ws.title.endswith('년_분기별상환예정') else ws.title
            if name not in template.sheetnames:continue
            sample=template[name]
            for attr in ('sheet_format','page_setup','page_margins','print_options','sheet_properties','views'):
                setattr(ws,attr,copy(getattr(sample,attr)))
            ws.sheet_state=sample.sheet_state
            ws.column_dimensions.clear()
            for d in sample.column_dimensions.values():
                for col in range(d.min,min(d.max,ws.max_column)+1):
                    target=ws.column_dimensions[get_column_letter(col)]
                    for attr in ('width','hidden','outlineLevel','collapsed','bestFit'):setattr(target,attr,getattr(d,attr))
            ws.row_dimensions.clear()
            for r,d in sample.row_dimensions.items():
                if r<=ws.max_row:
                    for attr in ('height','hidden','outlineLevel','collapsed'):setattr(ws.row_dimensions[r],attr,getattr(d,attr))
            ws.auto_filter.ref=ws.dimensions if sample.auto_filter.ref else None
            ws.print_title_rows=sample.print_title_rows;ws.print_title_cols=sample.print_title_cols
            for row in ws:
                total=ws.title in ('연도별현황','분기별현황') and row[0].value=='합계'
                if row[0].row==1:source_row=1
                elif total:source_row=sample.max_row
                elif name in ('요약','집계기준','선택연도_분기별상환예정'):source_row=min(row[0].row,sample.max_row)
                else:source_row=2
                for cell in row:
                    copy_cell_style(sample.cell(source_row,cell.column),cell)
                    # 상태는 샘플의 특정 연도가 아니라 새 집계 값에 따라 강조한다.
                    if not total and cell.value in ('완료','미완료'):
                        copy_cell_style(template['요약']['K5' if cell.value=='미완료' else 'K2'],cell)
        wb.active=wb.sheetnames.index('요약')
    finally:template.close()
