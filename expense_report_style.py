"""사용자 샘플의 계좌별 결과 열 너비·숨김 설정. 실제 거래자료는 포함하지 않는다."""
import json
from pathlib import Path
from openpyxl.utils import get_column_letter


def apply_expense_columns(workbook):
    settings=json.loads((Path(__file__).parent/'templates'/'expense_columns.json').read_text(encoding='utf-8'))
    for sheet in workbook:
        if sheet.title=='처리요약':continue
        for cell in sheet[1]:
            header=str(cell.value or '').strip()
            rule=settings.get('예적금명' if header=='계좌명' else header)
            if rule is None:continue
            dimension=sheet.column_dimensions[get_column_letter(cell.column)]
            dimension.width=rule['width'];dimension.hidden=rule['hidden'];dimension.bestFit=False
