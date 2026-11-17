from __future__ import annotations

import math
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


HEADER_FILL = PatternFill("solid", fgColor="DCE6F8")
MATCH_FILL = PatternFill("solid", fgColor="EAF6EC")
MISMATCH_FILL = PatternFill("solid", fgColor="FDEBEC")

STATEMENT_CONFIG = {
    "fund": {
        "title": "자금계산서 검증",
        "combined_col_idx": 2,  # C
        "school_col_idx": 8,    # I
        "combined_label": "C열",
        "school_label": "I열",
        "use_abs_compare": True,
    },
    "balance": {
        "title": "재무상태표 검증",
        "combined_col_idx": 2,  # C
        "school_col_idx": 4,    # E
        "combined_label": "C열",
        "school_label": "E열",
        "use_abs_compare": False,
    },
    "operation": {
        "title": "운영계산서 검증",
        "combined_col_idx": 2,  # C
        "school_col_idx": 4,    # E
        "combined_label": "C열",
        "school_label": "E열",
        "use_abs_compare": False,
    },
}


def _read_first_sheet(path: str) -> pd.DataFrame:
    from statement_io import read_frame
    return read_frame(path)


def _stringify_cell(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _parse_number(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        if value.is_nan() or not value.is_finite():
            return None
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return Decimal(str(value))
    text = str(value).replace(",", "")
    if not text.strip():
        return None
    try:
        parsed = Decimal(text.strip())
    except InvalidOperation:
        return None
    if parsed.is_nan() or not parsed.is_finite():
        return None
    return parsed


def _decimal_to_excel_number(value: Decimal | None):
    if value is None:
        return None
    if value.is_nan() or not value.is_finite():
        return None
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(normalized)


def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value.is_nan() or not value.is_finite():
        return ""
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(int(normalized), ",")
    return format(float(normalized), ",")


def _extract_column_records(path: str, value_col_idx: int) -> dict[str, list[dict[str, Any]]]:
    src = Path(path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {src}")

    df = _read_first_sheet(str(src))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row_idx in range(len(df.index)):
        raw = df.iat[row_idx, 0] if len(df.columns) > 0 else None
        key = _stringify_cell(raw)
        if not key:
            continue
        value = df.iat[row_idx, value_col_idx] if len(df.columns) > value_col_idx else None
        grouped[key].append(
            {
                "row_no": row_idx + 1,
                "raw_text": key,
                "amount": _parse_number(value),
            }
        )
    return dict(grouped)


def _extract_column_record_sequence(path: str, value_col_idx: int) -> list[dict[str, Any]]:
    src = Path(path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {src}")

    df = _read_first_sheet(str(src))
    rows: list[dict[str, Any]] = []

    for row_idx in range(len(df.index)):
        raw = df.iat[row_idx, 0] if len(df.columns) > 0 else None
        key = _stringify_cell(raw)
        if not key:
            continue
        value = df.iat[row_idx, value_col_idx] if len(df.columns) > value_col_idx else None
        rows.append(
            {
                "row_no": row_idx + 1,
                "raw_text": key,
                "amount": _parse_number(value),
            }
        )
    return rows


def _join_values(records: list[dict[str, Any]], amount_label: str) -> str:
    if not records:
        return ""
    lines = []
    for item in records:
        amount_text = _format_decimal(item.get("amount"))
        lines.append(f"{item['row_no']}행: {item['raw_text']} | {amount_label}={amount_text}")
    return "\n".join(lines)


def build_combined_statement_verify_workbook(
    statement_type: str,
    combined_source_path: str,
    school_source_path: str,
    out_path: str,
) -> tuple[str, dict[str, Any]]:
    config = STATEMENT_CONFIG.get(statement_type)
    if not config:
        raise ValueError("지원하지 않는 검증 구분입니다.")

    school_records = _extract_column_records(school_source_path, value_col_idx=int(config["school_col_idx"]))
    combined_records = _extract_column_records(combined_source_path, value_col_idx=int(config["combined_col_idx"]))
    school_sequence = _extract_column_record_sequence(school_source_path, value_col_idx=int(config["school_col_idx"]))

    all_keys = set(school_records) | set(combined_records)
    if not all_keys:
        raise ValueError("비교할 A열 텍스트를 찾지 못했습니다.")

    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = str(config["title"])
    ws.append(["비교 키", "대학재무제표 A열 값", "합산재무제표 A열 값", "대학 건수", "합산 건수", "일치 여부", "비고"])

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")

    items: list[dict[str, Any]] = []
    matched = 0
    mismatched = 0
    used_combined_counts: dict[str, int] = defaultdict(int)

    for school_item in school_sequence:
        key = school_item["raw_text"]
        combined_list = combined_records.get(key, [])
        idx = used_combined_counts[key]
        combined_item = combined_list[idx] if idx < len(combined_list) else None
        used_combined_counts[key] += 1

        school_amount = school_item.get("amount")
        combined_amount = combined_item.get("amount") if combined_item else None

        if combined_item and school_amount is not None and combined_amount is not None:
            if bool(config["use_abs_compare"]):
                school_compare = abs(school_amount or Decimal("0"))
                combined_compare = abs(combined_amount or Decimal("0"))
            else:
                school_compare = school_amount or Decimal("0")
                combined_compare = combined_amount or Decimal("0")
            diff = school_compare - combined_compare
            is_match = diff == 0
            note = "" if is_match else "금액 불일치"
        else:
            diff = None
            is_match = False
            note = "금액 확인 필요" if combined_item else "합산재무제표에 없음"

        if is_match:
            matched += 1
        else:
            mismatched += 1

        school_values = _join_values([school_item], str(config["school_label"]))
        combined_values = _join_values([combined_item] if combined_item else [], str(config["combined_label"]))

        ws.append([
            key,
            school_values,
            combined_values,
            1,
            1 if combined_item else 0,
            "일치" if is_match else "불일치",
            note,
        ])
        items.append(
            {
                "key": key,
                "school_values": school_values,
                "combined_values": combined_values,
                "school_count": 1,
                "combined_count": 1 if combined_item else 0,
                "school_amount": _decimal_to_excel_number(school_amount),
                "combined_amount": _decimal_to_excel_number(combined_amount),
                "diff_amount": _decimal_to_excel_number(diff),
                "is_match": is_match,
                "note": note,
            }
        )

    for key, combined_list in combined_records.items():
        start_idx = used_combined_counts.get(key, 0)
        for combined_item in combined_list[start_idx:]:
            combined_amount = combined_item.get("amount")
            mismatched += 1
            combined_values = _join_values([combined_item], str(config["combined_label"]))
            ws.append([
                key,
                "",
                combined_values,
                0,
                1,
                "불일치",
                "대학재무제표에 없음",
            ])
            items.append(
                {
                    "key": key,
                    "school_values": "",
                    "combined_values": combined_values,
                    "school_count": 0,
                    "combined_count": 1,
                    "school_amount": None,
                    "combined_amount": _decimal_to_excel_number(combined_amount),
                    "diff_amount": None,
                    "is_match": False,
                    "note": "대학재무제표에 없음",
                }
            )

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        fill = MATCH_FILL if row[5].value == "일치" else MISMATCH_FILL
        for cell in row:
            cell.fill = fill
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        row[3].alignment = Alignment(horizontal="center", vertical="top")
        row[4].alignment = Alignment(horizontal="center", vertical="top")
        row[5].alignment = Alignment(horizontal="center", vertical="top")

    ws.freeze_panes = "A2"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 42
    ws.column_dimensions["C"].width = 42
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 12
    ws.column_dimensions["F"].width = 12
    ws.column_dimensions["G"].width = 18

    for row in ws:
        for cell in row:
            if isinstance(cell.value,str):cell.data_type='s'
    ws.auto_filter.ref=ws.dimensions
    wb.save(str(out));wb.close()

    summary = {
        "mode": statement_type,
        "total_items": len(items),
        "matched_items": matched,
        "mismatched_items": mismatched,
        "items": items,
    }
    return str(out), summary
