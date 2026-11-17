"""기부금 결과 샘플에서 추출한 데이터 없는 서식을 적용한다."""
from copy import copy
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from loan_report_style import copy_cell_style


def apply_donation_sample(workbook):
    template=load_workbook(Path(__file__).parent/'templates/donation_report_style.xlsx')
    try:
        for ws in workbook:
            # 샘플에 없는 대학원 분류도 같은 공통 양식을 사용한다.
            # 캐피탈캠페인·현물기부금 샘플은 빈 시트라 데이터용 열 너비가 없었다.
            # 지정기부금에서 이동하는 자료이므로 동일한 전체 양식을 적용한다.
            sample_name='지정기부금' if ws.title in ('캐피탈캠페인','현물기부금') else ws.title
            sample=template[sample_name] if sample_name in template.sheetnames else template['교비일반장학']
            for attr in ('sheet_format','page_setup','page_margins','print_options','sheet_properties'):
                setattr(ws,attr,copy(getattr(sample,attr)))
            ws.column_dimensions.clear()
            for dimension in sample.column_dimensions.values():
                for col in range(dimension.min,min(dimension.max,ws.max_column)+1):
                    target=ws.column_dimensions[get_column_letter(col)]
                    for attr in ('width','hidden','outlineLevel','collapsed','bestFit'):
                        setattr(target,attr,getattr(dimension,attr))
            ws.sheet_view.zoomScale=sample.sheet_view.zoomScale
            ws.sheet_view.showGridLines=sample.sheet_view.showGridLines
            ws.freeze_panes='A2';ws.sheet_view.topLeftCell='A1'
            ws.print_title_rows=sample.print_title_rows;ws.print_title_cols=sample.print_title_cols
            for row in ws:
                is_total=ws.title!='처리요약' and row[0].row==ws.max_row and ws.cell(row[0].row,10).value=='합계'
                source_row=1 if row[0].row==1 else (3 if is_total else 2)
                ws.row_dimensions[row[0].row].height=sample.row_dimensions[source_row].height
                for cell in row:
                    # 금액은 현재 값에 따라 정수/소수 서식을 유지한다.
                    number_format=cell.number_format
                    copy_cell_style(sample.cell(source_row,cell.column),cell)
                    if cell.data_type=='n' and cell.value is not None and not is_total:
                        cell.number_format=number_format
            # 합계 행은 필터 범위에서 제외한 기존 범위를 유지한다.
        workbook.active=0
    finally:
        template.close()
