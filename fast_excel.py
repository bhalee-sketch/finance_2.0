"""openpyxl 3.1.5의 변환 규칙을 유지하는 단일 패스 원본 값/수식 검증."""
from openpyxl import load_workbook
from openpyxl.worksheet._reader import WorkSheetParser,FORMULA_TAG


def validated_rows(path):
    class CheckedParser(WorkSheetParser):
        def parse_cell(self,element):
            result=super().parse_cell(element)
            if result['data_type']=='e':raise ValueError(f'{path.name}: Excel 오류 값이 있습니다.')
            if element.find(FORMULA_TAG) is not None and result['value'] is None:
                raise ValueError(f'{path.name} {element.get("r", "")}: 수식 계산값이 없습니다. Excel에서 계산 후 저장하세요.')
            return result
    wb=load_workbook(path,read_only=True,data_only=True)
    try:
        sheet=wb.worksheets[0];width=sheet.max_column or 0;counter=1
        with sheet._get_source() as source:
            parser=CheckedParser(source,sheet._shared_strings,data_only=True,epoch=wb.epoch,
                                 date_formats=wb._date_formats,timedelta_formats=wb._timedelta_formats)
            for index,cells in parser.parse():
                while counter<index:
                    yield [None]*width;counter+=1
                size=max([width]+[c['column'] for c in cells]);row=[None]*size
                for cell in cells:row[cell['column']-1]=cell['value']
                yield row;counter=index+1
    finally:wb.close()
