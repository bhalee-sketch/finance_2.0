from __future__ import annotations

import re
from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


TYPE_PREFIX = {
    "fund": "자금계산서",
    "balance": "재무상태표",
    "operation": "운영계산서",
    "trial": "합계잔액시산표",
}

TYPE_LABEL = {
    "fund": "자금계산서",
    "balance": "재무상태표",
    "operation": "운영계산서",
    "trial": "합계잔액시산표",
}

SCOPE_SUFFIX = {
    "all": "전체",
    "tuition": "등록금",
    "non_tuition": "비등록금",
}

TOTAL_TARGETS = {
    "자금수입총계",
    "자금지출총계",
    "자산총계",
    "운영수익총계",
    "부채와기본금총계",
    "운영비용총계",
    "비용총계",
}

_THIN = Side(style="thin", color="DCE2EF")
BORDER_ALL = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
FILL_HEADER = PatternFill(fill_type="solid", fgColor="F8FAFF")
FILL_GWAN = PatternFill(fill_type="solid", fgColor="DCE7FF")
FILL_HANG = PatternFill(fill_type="solid", fgColor="EAF1FF")
FILL_TOTAL = PatternFill(fill_type="solid", fgColor="E7F5EB")
FILL_MARKER_ANGLE = PatternFill(fill_type="solid", fgColor="DCE7FF")
FILL_MARKER_PAREN = PatternFill(fill_type="solid", fgColor="EEF4FF")


def _normalize_subject(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).replace("[", "").replace("]", "")


def _is_zero_like(value: Any) -> bool:
    raw = str(value or "").strip()
    if raw == "":
        return False
    normalized = raw.replace(",", "")
    if not re.match(r"^[-+]?\d+(\.\d+)?$", normalized):
        return False
    return float(normalized) == 0.0


def _is_numeric_like(value: Any) -> bool:
    raw = str(value or "").strip()
    if raw == "":
        return False
    normalized = raw.replace(",", "")
    return bool(re.match(r"^[-+]?\d+(\.\d+)?$", normalized))


def _is_zero_or_empty(value: Any) -> bool:
    raw = str(value or "").strip()
    return raw == "" or _is_zero_like(raw)


def _desktop_dir(project_root: Path) -> Path:
    one_drive_desktop = Path.home() / "OneDrive" / "Desktop"
    if one_drive_desktop.exists():
        return one_drive_desktop
    desktop = Path.home() / "Desktop"
    if desktop.exists():
        return desktop
    return project_root


def _safe_sheet_title(name: str) -> str:
    safe = re.sub(r'[:\\/*?\[\]]', "_", name).strip()
    return safe[:31] if len(safe) > 31 else safe


def _apply_print_margins(ws: Any) -> None:
    # openpyxl page margins use inches; these values match the requested cm settings.
    ws.page_margins.top = 1.8 / 2.54
    ws.page_margins.header = 0.8 / 2.54
    ws.page_margins.left = 1 / 2.54
    ws.page_margins.right = 1 / 2.54
    ws.page_margins.bottom = 1.5 / 2.54
    ws.page_margins.footer = 0.8 / 2.54


def _apply_print_layout(ws: Any) -> None:
    ws.print_options.horizontalCentered = True
    ws.page_setup.paperSize = ws.PAPERSIZE_A4


def _part_bounds(type_key: str, rows: list[Any]) -> tuple[int, int]:
    subjects=[_normalize_subject(str((row or [''])[0])) for row in rows]
    for i,row in enumerate(rows):
        raw=re.sub(r'\s+','',str((row or [''])[0]))
        if raw.startswith(('[지출]','[부채와기본금]')):
            return i-1,i+1
    if type_key=='operation':
        end=next((i for i,s in enumerate(subjects) if s=='운영수익총계'),-1)
        start=next((i for i,s in enumerate(subjects) if s=='보수' and i>end),-1)
        return end,start
    if type_key=='balance':
        end=next((i for i,s in enumerate(subjects) if s=='자산총계'),-1)
        return (end,end+1) if end>=0 else (-1,-1)
    return -1,-1


def _build_filtered_sheets(
    bundle: dict[str, Any],
    year: str,
    type_key: str,
    scope_key: str,
    part_key: str,
) -> list[dict[str, Any]]:
    record = (bundle.get("by_year") or {}).get(year) or {}
    sheets = record.get("sheets") or []
    selected_prefix = TYPE_PREFIX.get(type_key, TYPE_PREFIX["fund"])
    selected_scope = SCOPE_SUFFIX.get(scope_key, SCOPE_SUFFIX["all"])

    filtered = []
    for sheet in sheets:
        name = str(sheet.get("name", ""))
        normalized = re.sub(r"\s+", "", name)
        if not normalized.startswith(selected_prefix):
            continue
        if f"({selected_scope})" not in normalized:
            continue
        filtered.append(sheet)

    result: list[dict[str, Any]] = []
    for sheet in filtered:
        raw_headers = list(sheet.get("headers") or [])
        all_rows = list(sheet.get("rows") or [])
        divider_index = -1
        for i, r in enumerate(all_rows):
            subject = re.sub(r"\s+", "", str((r or [""])[0]))
            if "[지출]" in subject:
                divider_index = i
                break

        part_rows = all_rows
        if part_key in ('upper','lower') and type_key!='trial':
            end,start=_part_bounds(type_key,all_rows)
            if end<0 or start<0:
                raise ValueError('수입/지출 또는 자산/부채 구분 위치를 찾지 못했습니다. 전체로 조회하여 원본을 확인하세요.')
            part_rows=all_rows[:end+1] if part_key=='upper' else all_rows[start:]
        else:
            part_rows = [r for i, r in enumerate(all_rows) if i != divider_index]

        is_trial = type_key == "trial"
        if is_trial:
            idxs = [1, 4, 7, 11, 15, 19]
            headers = ["잔액", "합계", "코드", "과목", "합계", "잔액"]
            rows: list[dict[str, Any]] = []
            for r in part_rows:
                mapped = [r[i] if i < len(r) else "" for i in idxs]
                all_empty = all(str(c or "").strip() == "" for c in mapped)
                amount_cells = [mapped[0], mapped[1], mapped[4], mapped[5]]
                has_amount = any(_is_numeric_like(c) for c in amount_cells)
                amounts_zero_or_empty = all(_is_zero_or_empty(c) for c in amount_cells)
                header_like = (
                    "잔액" in _normalize_subject(mapped[0])
                    and "합계" in _normalize_subject(mapped[1])
                    and "코드" in _normalize_subject(mapped[2])
                    and "과목" in _normalize_subject(mapped[3])
                )
                if all_empty or (not has_amount) or amounts_zero_or_empty or header_like:
                    continue
                subject = str(mapped[3]).strip()
                row_class = ""
                if subject.startswith("<"):
                    row_class = "marker_angle"
                elif subject.startswith("("):
                    row_class = "marker_paren"
                for index in (0,1,4,5):
                    if mapped[index] is None or not str(mapped[index]).strip():mapped[index]="0"
                rows.append({"values": mapped, "class": row_class, "indent": 0})
            result.append({"name": sheet.get("name", "Sheet"), "headers": headers, "rows": rows, "is_trial": True})
            continue

        subject_indent = str((raw_headers[0] if raw_headers else "")).strip() == "과목"
        rows = []
        for r in part_rows:
            headers_for_row = [str(h or "").upper() for h in raw_headers[1:]]
            data_cells = list((r or [])[1:])
            judged = [c for idx, c in enumerate(data_cells) if idx < len(headers_for_row) and "RATE" not in headers_for_row[idx]]
            if judged and all(_is_zero_like(c) for c in judged):
                continue

            values = list(r)
            row_class = ""
            indent_level = 0
            if subject_indent:
                subject_raw = str(values[0] if values else "")
                leading = len(subject_raw) - len(subject_raw.lstrip(" "))
                subject_text = subject_raw.strip()
                if values:
                    values[0] = subject_text
                if subject_text and leading < 5:
                    row_class = "gwan"
                elif subject_text and 5 <= leading < 10:
                    row_class = "hang"
                    indent_level = 1
                elif subject_text and leading >= 10:
                    row_class = "mok"
                    indent_level = 2

                normalized = _normalize_subject(subject_text)
                if normalized in TOTAL_TARGETS:
                    row_class = "total_green"
                if subject_text.startswith("<"):
                    row_class = "marker_angle"
                elif subject_text.startswith("("):
                    row_class = "marker_paren"
            # 조회/현재 화면 저장에서만 빈 금액을 0으로 표시한다.
            # 원본 레코드와 결산 분석의 결측 판단은 변경하지 않는다.
            if values and str(values[0] or '').strip() and (row_class=='total_green' or not str(values[0]).strip().startswith(('[','<'))):
                values += [''] * max(0,len(raw_headers)-len(values))
                for index in range(1,len(values)):
                    if values[index] is None or not str(values[index]).strip():values[index]="0"
            rows.append({"values": values, "class": row_class, "indent": indent_level})
        result.append({"name": sheet.get("name", "Sheet"), "headers": raw_headers, "rows": rows, "is_trial": False})
    return result


def _apply_row_fill(ws: Any, row_idx: int, width: int, row_class: str) -> None:
    if row_class == "gwan":
        fill = FILL_GWAN
    elif row_class == "hang":
        fill = FILL_HANG
    elif row_class == "total_green":
        fill = FILL_TOTAL
    elif row_class == "marker_angle":
        fill = FILL_MARKER_ANGLE
    elif row_class == "marker_paren":
        fill = FILL_MARKER_PAREN
    else:
        return
    for c in range(1, width + 1):
        ws.cell(row=row_idx, column=c).fill = copy(fill)


def export_statement_excel(
    bundle: dict[str, Any],
    project_root: Path,
    year: str,
    type_key: str,
    scope_key: str,
    part_key: str,
    output_path=None,
) -> Path:
    sheets = _build_filtered_sheets(bundle, year, type_key, scope_key, part_key)
    if not sheets:
        raise ValueError("내려받을 데이터가 없습니다.")

    wb = Workbook()
    wb.remove(wb.active)

    title_type = TYPE_LABEL.get(type_key, TYPE_LABEL["fund"])
    scope_label = SCOPE_SUFFIX.get(scope_key, SCOPE_SUFFIX["all"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{year}회계연도_{scope_label}_{timestamp}.xlsx"
    from result_paths import result_path
    out_path = Path(output_path) if output_path else result_path('재무제표 조회')

    for sheet in sheets:
        ws = wb.create_sheet(_safe_sheet_title(str(sheet["name"])))
        headers = list(sheet["headers"])
        rows = list(sheet["rows"])
        col_count = max(len(headers), 1)

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
        ws.cell(row=1, column=1, value=f"{year}회계연도 {scope_label} - {title_type}")
        ws.row_dimensions[1].height = 28
        ws.cell(row=1, column=1).font = Font(size=14, bold=True)
        ws.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")

        header_row = 3
        ws.row_dimensions[header_row].height = 22
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=c, value=str(h))
            cell.data_type="s"
            cell.font = Font(size=11, bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = copy(FILL_HEADER)
            cell.border = copy(BORDER_ALL)

        data_start = header_row + 1
        max_lens = [len(str(h or "")) for h in headers]
        for r_idx, row_info in enumerate(rows, data_start):
            values = list(row_info["values"])
            ws.row_dimensions[r_idx].height = 20
            for c in range(1, col_count + 1):
                text = str(values[c - 1]) if c - 1 < len(values) else ""
                max_lens[c - 1] = max(max_lens[c - 1], len(text))
                cell = ws.cell(row=r_idx, column=c, value=text)
                cell.data_type="s"
                cell.font = Font(size=10)
                cell.border = copy(BORDER_ALL)

                if sheet["is_trial"]:
                    if c in (1, 2, 5, 6):
                        align = Alignment(horizontal="right", vertical="center")
                    elif c in (3, 4):
                        align = Alignment(horizontal="center", vertical="center")
                    else:
                        align = Alignment(horizontal="left", vertical="center")
                else:
                    if type_key in ("fund", "balance", "operation") and c != 1:
                        align = Alignment(horizontal="right", vertical="center")
                    else:
                        align = Alignment(horizontal="left", vertical="center")
                    if c == 1:
                        indent_level = int(row_info.get("indent", 0))
                        align = Alignment(horizontal="left", vertical="center", indent=indent_level)
                cell.alignment = align

            _apply_row_fill(ws, r_idx, col_count, str(row_info.get("class", "")))

        for idx, max_len in enumerate(max_lens, 1):
            width = min(max(10, int(max_len * 1.3) + 2), 42)
            ws.column_dimensions[get_column_letter(idx)].width = width
        _apply_print_layout(ws)
        _apply_print_margins(ws)

    try:
        wb.save(out_path)
        return out_path
    finally:wb.close()


def export_all_year_excel(
    bundle: dict[str, Any],
    project_root: Path,
    year: str,
    output_path=None,
) -> Path:
    record = (bundle.get("by_year") or {}).get(year) or {}
    sheets = list(record.get("sheets") or [])
    if not sheets:
        raise ValueError("내려받을 데이터가 없습니다.")

    wb = Workbook()
    wb.remove(wb.active)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"{year}회계연도_전체_{timestamp}.xlsx"
    from result_paths import result_path
    out_path = Path(output_path) if output_path else result_path('재무제표 조회')

    for sheet in sheets:
        ws = wb.create_sheet(_safe_sheet_title(str(sheet.get("name", "Sheet"))))
        headers = list(sheet.get("headers") or [])
        rows = list(sheet.get("rows") or [])
        col_count = max(len(headers), 1)

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_count)
        ws.cell(row=1, column=1, value=f"{year}회계연도 - {sheet.get('name', '')}")
        ws.row_dimensions[1].height = 28
        ws.cell(row=1, column=1).font = Font(size=14, bold=True)
        ws.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")

        header_row = 3
        ws.row_dimensions[header_row].height = 22
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=header_row, column=c, value=str(h))
            cell.data_type="s"
            cell.font = Font(size=11, bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = copy(FILL_HEADER)
            cell.border = copy(BORDER_ALL)

        max_lens = [len(str(h or "")) for h in headers]
        for r_idx, row in enumerate(rows, header_row + 1):
            ws.row_dimensions[r_idx].height = 20
            for c in range(1, col_count + 1):
                text = str(row[c - 1]) if c - 1 < len(row) else ""
                max_lens[c - 1] = max(max_lens[c - 1], len(text))
                cell = ws.cell(row=r_idx, column=c, value=text)
                cell.data_type="s"
                cell.font = Font(size=10)
                cell.border = copy(BORDER_ALL)
                cell.alignment = Alignment(horizontal="left", vertical="center")

        for idx, max_len in enumerate(max_lens, 1):
            width = min(max(10, int(max_len * 1.3) + 2), 42)
            ws.column_dimensions[get_column_letter(idx)].width = width
        _apply_print_layout(ws)
        _apply_print_margins(ws)

    try:
        wb.save(out_path)
        return out_path
    finally:wb.close()
