from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


BALANCE_SHEET_MAPPING: dict[str, tuple] = {
    "현금": ("현금및예금명세서(전체)", ["현금소계"], 7),
    "예금": ("현금및예금명세서(전체)", ["예금소계"], 7),
    "선급금": ("선급금명세서", ["합계"], None),
    "미수금": ("미수금및기타유동자산명세서", ["미수금소계"], 4),
    "가지급금": ("가지급금명세서", ["합계"], None),
    "선급법인세": ("선급법인세명세서", ["합계"], None, "합계", True),
    "기타유동자산": ("미수금및기타유동자산명세서", ["기타유동자산소계"], 4),
    "투자유가증권": ("투자유가증권 명세서", ["합계"], 7),
    "전신전화보증금": ("투자와기타자산명세서", "H11"),
    "기타자산": ("투자와기타자산명세서", "H13"),
    "임의연구기금": ("투자와기타자산명세서", "H17"),
    "임의건축기금": ("투자와기타자산명세서", "H18"),
    "임의장학기금": ("투자와기타자산명세서", "H21"),
    "임의특정목적기금": ("투자와기타자산명세서", "H23"),
    "토지": ("유형고정자산명세서", ["토지"], 4),
    "건물": ("유형고정자산명세서", ["건물"], 4),
    "건물감가상각누계액": ("유형고정자산명세서", ["건물"], 5),
    "사용수익권": ("유형고정자산명세서", ["건물"], 6),
    "구축물": ("유형고정자산명세서", ["구축물"], 4),
    "구축물감가상각누계액": ("유형고정자산명세서", ["구축물"], 5),
    "기계기구": ("유형고정자산명세서", ["기계기구"], 4),
    "기계기구감가상각누계액": ("유형고정자산명세서", ["기계기구"], 5),
    "집기비품": ("유형고정자산명세서", ["집기비품"], 4),
    "집기비품감가상각누계액": ("유형고정자산명세서", ["집기비품"], 5),
    "차량운반구": ("유형고정자산명세서", ["차량운반구"], 4),
    "차량운반구감가상각누계액": ("유형고정자산명세서", ["차량운반구"], 5),
    "도서": ("유형고정자산명세서", ["도서"], 4),
    "도서감가상각누계액": ("유형고정자산명세서", ["도서"], 5),
    "건설중인자산": ("유형고정자산명세서", ["건설중인자산"], 4),
    "무형고정자산": ("무형고정자산명세서", ["합계"], 6),
    "단기차입금": ("단기(장기)차입금명세서", "I11"),
    "예수금": ("예수금명세서", ["합계"], None),
    "선수금": ("선수금명세서", ["합계"], None),
    "미지급금": ("미지급금명세서", ["합계"], None),
    "가수금": ("가수금", ["합계"], None),
    "장기차입금": ("단기(장기)차입금명세서", "I19"),
    "임대보증금": ("기타고정부채명세서", ["임대보증금소계"], 6),
    "장기미지급금": ("기타고정부채명세서", ["장기미지급금 소계"], 6),
    "기타고정부채": ("기타고정부채명세서", ["기타고정부채 소 계"], 6),
    "학교채": ("학교채명세서", ["합계"], None),
    "출연기본금": ("기본금명세서", "G4"),
    "임의적립금": ("기본금명세서", "G11"),
    "기본금조정": ("기본금명세서", "G15"),
    "운영차액": ("기본금명세서", "G18"),
    "임의연구적립금": ("적립금명세서", "H11"),
    "임의건축적립금": ("적립금명세서", "H12+H13"),
    "임의장학적립금": ("적립금명세서", "H14"),
    "임의특정목적적립금": ("적립금명세서", "H16"),
}

INCOME_STMT_MAPPING: dict[str, tuple] = {
    "등록금수입": ("등록금명세서", ["등 록 금 수 입 총 계"], 11),
    "수강료수입": ("등록금명세서", ["수강료수입 총계"], 11),
    "경상비전입금": ("전입금명세서", "F9"),
    "법정부담전입금": ("전입금명세서", "F22"),
    "등록금회계전입금": ("전입금명세서", "F37"),
    "산학협력단전입금": ("전입금명세서", "F40"),
    "감가상각비": ("고정자산 감가상각비명세서", "E14"),
}


def _read_excel_fast(path: str, sheet_name: str) -> pd.DataFrame:
    from statement_io import read_frame
    return read_frame(path,sheet_name)


def _clean_number(val: Any) -> float | None:
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        n = float(val)
        import math
        return n if math.isfinite(n) else None
    s = str(val).replace(",", "").replace(" ", "").strip()
    if not s:
        return None
    try:
        import math
        n=float(s)
        return n if math.isfinite(n) else None
    except ValueError:
        return None


def _find_col_by_name(df: pd.DataFrame, col_name: str) -> int | None:
    target = str(col_name).replace(" ", "").strip()
    for row_idx in range(min(5, len(df))):
        row = df.iloc[row_idx]
        for col_idx, cell in enumerate(row):
            if pd.isna(cell):
                continue
            if str(cell).replace(" ", "").strip() == target:
                return col_idx
    return None


def _parse_cell_ref(cell_ref: str) -> tuple[int, int]:
    match = re.match(r"^([A-Z]+)(\d+)$", str(cell_ref).upper())
    if not match:
        raise ValueError(f"Invalid cell reference: {cell_ref}")
    col_str, row_str = match.groups()
    col_idx = 0
    for c in col_str:
        col_idx = col_idx * 26 + (ord(c) - ord("A") + 1)
    return int(row_str) - 1, col_idx - 1


def _extract_cell_value(df: pd.DataFrame, cell_ref: str) -> float | None:
    try:
        if "+" in str(cell_ref):
            total = 0.0
            for ref in str(cell_ref).split("+"):
                r, c = _parse_cell_ref(ref.strip())
                if r < len(df) and c < len(df.columns):
                    val = _clean_number(df.iloc[r, c])
                    if val is None:return None
                    total += val
                else:return None
            return total
        r, c = _parse_cell_ref(cell_ref)
        if r < len(df) and c < len(df.columns):
            return _clean_number(df.iloc[r, c])
    except Exception:
        return None
    return None


def _pick_amount_from_row(row, base_col_idx: int, amount_col: int | None) -> float:
    if amount_col is not None and len(row) > amount_col:
        val = _clean_number(row.iloc[amount_col])
        return val
    for j in range(base_col_idx + 1, len(row)):
        val = _clean_number(row.iloc[j])
        if val is not None:
            return val
    return None


def _extract_total_from_sheet(
    df: pd.DataFrame,
    keywords: list[str],
    amount_col: int | None = None,
    amount_col_name: str | None = None,
    find_last: bool = False,
) -> float | None:
    if amount_col_name:
        found_col = _find_col_by_name(df, amount_col_name)
        if found_col is not None:
            amount_col = found_col

    exact_match = None
    exact_match_found = False
    partial_match = None
    partial_match_found = False

    for _, row in df.iterrows():
        for col_idx, cell in enumerate(row):
            if pd.isna(cell):
                continue
            cell_str = str(cell).replace(" ", "").strip()
            for kw in keywords:
                kw_clean = str(kw).replace(" ", "").strip()
                if cell_str == kw_clean:
                    if find_last or not exact_match_found:
                        exact_match_found = True
                        exact_match = _pick_amount_from_row(row, col_idx, amount_col)
                elif kw_clean in cell_str:
                    if find_last or not partial_match_found:
                        partial_match_found = True
                        partial_match = _pick_amount_from_row(row, col_idx, amount_col)

    if exact_match_found:
        return exact_match
    if partial_match_found:
        return partial_match
    return None


def _list_excel_sheet_names(path: str) -> list[str]:
    from statement_io import sheet_names
    return sheet_names(path)


def _extract_fs_amounts(fs_path: str, sheet_name: str) -> dict[str, float | None]:
    df = _read_excel_fast(fs_path, sheet_name)
    out: dict[str, float | None] = {}
    for _, row in df.iterrows():
        account = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if not account:
            continue
        out[account] = _clean_number(row.iloc[4]) if len(row) > 4 else None
    return out


def _extract_fs_amount_by_column(fs_path: str, sheet_name: str, account_name: str, column_name: str) -> float | None:
    df = _read_excel_fast(fs_path, sheet_name)
    if df.empty:
        return None
    target_account = str(account_name).replace(" ", "").strip()
    target_col = str(column_name).replace(" ", "").strip()
    fixed_col_map = {
        "등록금": 1,      # B열
        "비등록금": 2,    # C열
    }
    amount_col = fixed_col_map.get(target_col)
    if amount_col is None:
        return None

    for row_idx in range(1, len(df)):
        account = str(df.iloc[row_idx, 0]).replace(" ", "").strip() if pd.notna(df.iloc[row_idx, 0]) else ""
        if account != target_account:
            continue
        if amount_col >= len(df.columns):
            return None
        return _clean_number(df.iloc[row_idx, amount_col])
    return None


def _verify_by_mapping(
    fs_amounts: dict[str, float | None],
    supp_path: str,
    mapping_dict: dict[str, tuple],
    category_name: str,
) -> list[dict[str, Any]]:
    supp_sheets = set(_list_excel_sheet_names(supp_path))
    sheet_cache: dict[str, pd.DataFrame] = {}
    items: list[dict[str, Any]] = []

    for account, mapping in mapping_dict.items():
        sheet_name = str(mapping[0])
        fs_amount = fs_amounts.get(account)
        supp_amount = None

        if sheet_name in supp_sheets:
            supp_df = sheet_cache.get(sheet_name)
            if supp_df is None:
                supp_df = _read_excel_fast(supp_path, sheet_name)
                sheet_cache[sheet_name] = supp_df

            if isinstance(mapping[1], str):
                supp_amount = _extract_cell_value(supp_df, mapping[1])
            else:
                keywords = mapping[1]
                amount_col = mapping[2] if len(mapping) > 2 else None
                amount_col_name = mapping[3] if len(mapping) > 3 else None
                find_last = bool(mapping[4]) if len(mapping) > 4 else False
                supp_amount = _extract_total_from_sheet(
                    supp_df,
                    keywords,
                    amount_col=amount_col,
                    amount_col_name=amount_col_name,
                    find_last=find_last,
                )

        fs_val = _clean_number(fs_amount) or 0.0
        supp_val = _clean_number(supp_amount) or 0.0
        use_abs = ("감가상각" in account) or ("사용수익권" in account)
        diff = abs(fs_val) - abs(supp_val) if use_abs else fs_val - supp_val
        complete = sheet_name in supp_sheets
        is_match = complete and abs(diff) < 1
        is_both_zero = complete and abs(fs_val) < 1 and abs(supp_val) < 1

        items.append(
            {
                "category": category_name,
                "account": account,
                "fs_amount": fs_val,
                "supp_amount": supp_val,
                "supp_sheet": sheet_name,
                "use_abs": use_abs,
                "diff": diff,
                "is_match": is_match,
                "is_both_zero": is_both_zero,
            }
        )

    return items


def _verify_unused_carry_forward_items(fs_path: str, balance_supp_path: str) -> list[dict[str, Any]]:
    custom_specs = [
        {
            "account": "미사용차기이월자금",
            "fs_sheet": "자금계산서(전체)",
            "fs_subject": "미사용차기이월자금",
            "fs_column": "등록금",
            "supp_sheet": "미사용자금(등록금)",
            "supp_cell": "D11",
            "category": "자금계산서(전체) B열 등록금",
            "sort_tag": "unused_carry_tuition",
        },
        {
            "account": "미사용차기이월자금",
            "fs_sheet": "자금계산서(전체)",
            "fs_subject": "미사용차기이월자금",
            "fs_column": "비등록금",
            "supp_sheet": "미사용자금(비등록금)",
            "supp_cell": "D11",
            "category": "자금계산서(전체) C열 비등록금",
            "sort_tag": "unused_carry_nontuition",
        },
    ]
    supp_sheets = set(_list_excel_sheet_names(balance_supp_path))
    sheet_cache: dict[str, pd.DataFrame] = {}
    items: list[dict[str, Any]] = []

    for spec in custom_specs:
        fs_amount = _extract_fs_amount_by_column(
            fs_path,
            spec["fs_sheet"],
            spec["fs_subject"],
            spec["fs_column"],
        )
        supp_amount = None

        if spec["supp_sheet"] in supp_sheets:
            supp_df = sheet_cache.get(spec["supp_sheet"])
            if supp_df is None:
                supp_df = _read_excel_fast(balance_supp_path, spec["supp_sheet"])
                sheet_cache[spec["supp_sheet"]] = supp_df
            supp_amount = _extract_cell_value(supp_df, spec["supp_cell"])

        fs_val = _clean_number(fs_amount) or 0.0
        supp_val = _clean_number(supp_amount) or 0.0
        diff = fs_val - supp_val
        complete = spec["supp_sheet"] in supp_sheets
        is_match = complete and abs(diff) < 1
        is_both_zero = complete and abs(fs_val) < 1 and abs(supp_val) < 1

        items.append(
            {
                "category": spec["category"],
                "account": spec["account"],
                "fs_amount": fs_val,
                "supp_amount": supp_val,
                "supp_sheet": spec["supp_sheet"],
                "use_abs": False,
                "diff": diff,
                "is_match": is_match,
                "is_both_zero": is_both_zero,
                "sort_tag": spec["sort_tag"],
            }
        )

    return items


def _reorder_statement_appendix_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    custom_sort_tags = [
        "unused_carry_tuition",
        "unused_carry_nontuition",
    ]
    custom_items = [item for item in items if str(item.get("sort_tag") or "") in custom_sort_tags]
    if not custom_items:
        return items

    remaining = [item for item in items if str(item.get("sort_tag") or "") not in custom_sort_tags]
    insert_at = next(
        (idx for idx, item in enumerate(remaining) if str(item.get("account") or "") == "등록금수입"),
        len(remaining),
    )
    ordered_custom = []
    for sort_tag in custom_sort_tags:
        ordered_custom.extend(item for item in custom_items if str(item.get("sort_tag") or "") == sort_tag)
    return remaining[:insert_at] + ordered_custom + remaining[insert_at:]


def run_statement_appendix_verification(
    project_root: Path | str,
    fs_path: str,
    balance_supp_path: str | None = None,
    operation_supp_path: str | None = None,
) -> dict[str, Any]:
    _ = project_root
    if not fs_path:
        raise ValueError("재무제표 파일 경로가 없습니다.")
    if not balance_supp_path and not operation_supp_path:
        raise ValueError("부속명세서 파일을 최소 1개 선택하세요.")

    all_items: list[dict[str, Any]] = []

    if balance_supp_path:
        all_items.extend(_verify_unused_carry_forward_items(fs_path, balance_supp_path))
        fs_amounts_bs = _extract_fs_amounts(fs_path, "재무상태표(전체)")
        all_items.extend(_verify_by_mapping(fs_amounts_bs, balance_supp_path, BALANCE_SHEET_MAPPING, "재무상태표"))

    if operation_supp_path:
        fs_amounts_is = _extract_fs_amounts(fs_path, "운영계산서(전체)")
        all_items.extend(_verify_by_mapping(fs_amounts_is, operation_supp_path, INCOME_STMT_MAPPING, "운영계산서"))

    items = [it for it in all_items if not bool(it.get("is_both_zero"))]
    items = _reorder_statement_appendix_items(items)
    total = len(items)
    matched = sum(1 for it in items if bool(it.get("is_match")))
    mismatched = total - matched

    return {"total": total, "matched": matched, "mismatched": mismatched, "items": items}
