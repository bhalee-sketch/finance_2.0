from __future__ import annotations

import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


YEAR_PATTERN = re.compile(r"(20\d{2})")


def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _format_number_by_excel(value: float, number_format: str) -> str:
    fmt = (number_format or "").strip()
    if not fmt or fmt.lower() == "general":
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    if "%" in fmt:
        decimals = 0
        if "." in fmt:
            decimals = len(fmt.split(".", 1)[1].split("%", 1)[0].replace("#", "").replace(",", ""))
        return f"{value * 100:.{decimals}f}%"

    decimals = 0
    if "." in fmt:
        decimals = len(fmt.split(".", 1)[1].split(";", 1)[0].replace("#", "").replace(",", ""))

    use_comma = "," in fmt
    if use_comma:
        return f"{value:,.{decimals}f}" if decimals > 0 else f"{value:,.0f}"
    return f"{value:.{decimals}f}" if decimals > 0 else (str(int(value)) if float(value).is_integer() else str(value))


def _cell_display_text(cell: Any) -> str:
    value = cell.value
    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")

    if isinstance(value, (int, float)):
        return _format_number_by_excel(float(value), getattr(cell, "number_format", ""))

    return _cell_to_text(value)


def _read_sheet(ws: Any) -> dict[str, Any]:
    max_col = max(int(ws.max_column or 1), 1)
    first_row = next(ws.iter_rows(min_row=1, max_row=1, max_col=max_col, values_only=False), ())
    headers = [_cell_display_text(cell) for cell in first_row]
    if not any(headers):
        headers = [f"컬럼{i + 1}" for i in range(max_col)]
    else:
        headers = [h if h else f"컬럼{i + 1}" for i, h in enumerate(headers)]

    rows: list[list[str]] = []
    for cells in ws.iter_rows(min_row=2, max_col=len(headers), values_only=False):
        row = [_cell_display_text(cell) for cell in cells]
        if not any(cell for cell in row):
            continue
        rows.append(row)

    return {"name": ws.title, "headers": headers, "rows": rows}


def _build_year_record(path: Path) -> dict[str, Any]:
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        sheets = [_read_sheet(ws) for ws in wb.worksheets]
    finally:
        wb.close()
    return {"sheets": sheets}


def load_statement_record_from_path(path: Path) -> dict[str, Any]:
    return _build_year_record(path)


def extract_year_from_path(path: Path) -> str:
    matched = YEAR_PATTERN.search(path.name)
    return matched.group(1) if matched else ""


def load_statement_bundle(project_root: Path) -> dict[str, Any]:
    statements_dir = project_root / "data" / "statements"
    if not statements_dir.exists():
        statements_dir = project_root / "data-statement"

    files = []
    if statements_dir.exists():
        for p in sorted(statements_dir.glob("*.xlsx")):
            # Ignore temporary lock files created by Excel (e.g. "~$2024회계연도.xlsx")
            if p.name.startswith("~$"):
                continue
            files.append(p)
    by_year: dict[str, Any] = {}
    for path in files:
        matched = YEAR_PATTERN.search(path.name)
        if not matched:
            continue
        year = matched.group(1)
        by_year[year] = _build_year_record(path)

    years = sorted(by_year.keys())
    return {"years": years, "by_year": by_year}


def _to_float_or_zero(value: Any) -> float:
    text = str(value or "").replace(",", "").strip()
    if text == "":
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _read_settle_year(path: Path) -> dict[str, Any]:
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        sheets_data: dict[str, list[dict[str, Any]]] = {}
        for ws in wb.worksheets:
            headers = [str(c.value or "").strip() for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=False), ())]
            header_map = {name: idx for idx, name in enumerate(headers)}
            required = ["구분", "관", "항", "목", "전체", "등록금", "비등록금"]
            if any(k not in header_map for k in required):
                continue

            rows: list[dict[str, Any]] = []
            for r in ws.iter_rows(min_row=2, max_col=len(headers), values_only=False):
                vals = [c.value for c in r]
                row = {
                    "구분": str(vals[header_map["구분"]] or "").strip(),
                    "관": str(vals[header_map["관"]] or "").strip(),
                    "항": str(vals[header_map["항"]] or "").strip(),
                    "목": str(vals[header_map["목"]] or "").strip(),
                    "전체": _to_float_or_zero(vals[header_map["전체"]]),
                    "등록금": _to_float_or_zero(vals[header_map["등록금"]]),
                    "비등록금": _to_float_or_zero(vals[header_map["비등록금"]]),
                }
                if not (row["관"] or row["항"] or row["목"]):
                    continue
                rows.append(row)

            sheets_data[ws.title] = rows
    finally:
        wb.close()
    return {"sheets": sheets_data}


def load_settle_bundle(project_root: Path) -> dict[str, Any]:
    settle_dir = project_root / "data" / "settle"
    files = []
    if settle_dir.exists():
        for p in sorted(settle_dir.glob("*.xlsx")):
            # Ignore temporary lock files created by Excel.
            if p.name.startswith("~$"):
                continue
            files.append(p)
    by_year: dict[str, Any] = {}
    for p in files:
        matched = YEAR_PATTERN.search(p.name)
        if not matched:
            continue
        year = matched.group(1)
        by_year[year] = _read_settle_year(p)
    years = sorted(by_year.keys())
    return {"years": years, "by_year": by_year}
