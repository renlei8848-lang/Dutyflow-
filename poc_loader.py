"""
poc_loader.py — Phase 1: Data Loader
Reads the "清洗后数据" sheet from 晚自修排版.xlsx and returns List[TeacherRecord].

Module boundaries (from ARCHITECTURE.md):
  - No solver logic here.
  - No LLM calls at runtime.
  - No hardcoded sheet names or column names (all from PARAMS_REGISTRY.yaml).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Load configuration from PARAMS_REGISTRY.yaml (module-level, single read)
# ---------------------------------------------------------------------------
_REGISTRY_PATH = pathlib.Path(__file__).parent / ".dutyflow_meta" / "PARAMS_REGISTRY.yaml"

with _REGISTRY_PATH.open(encoding="utf-8") as _f:
    _CFG = yaml.safe_load(_f)

_SHEET_NAME: str = _CFG["data_loader"]["excel_output_sheet"]      # "清洗后数据"
_NAME_COL: str = _CFG["data_loader"]["teacher_name_column"]       # "姓名"
_DEFAULT_EXCEL_PATH: str = _CFG["clean_schedule"]["excel_path"]   # desktop path

# Required columns with static names — if any are absent the loader raises ValueError.
# Avg columns are excluded here because their names contain a dynamic month suffix
# (e.g. "月均次数/8月") and are resolved via fuzzy match after df is loaded.
_REQUIRED_COLS: tuple[str, ...] = (
    "序号", "姓名", "教学学科", "要求", "楼层",
    "是否班主任", "历史总次数", "历史周五次数", "历史周日次数",
)


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TeacherRecord:
    teacher_id: int        # 序号
    name: str              # 姓名
    subject: str           # 教学学科
    floor_zone: str        # 楼层 (normalized: "1楼" | "2-3楼" | "4-5楼")
    tags: frozenset[str]   # 要求 tags: {"不排了"} | {"不要周日"} | {"不要周五"} | {}
    is_banzhuren: bool     # True if teacher is a 班主任
    history_total: int     # 历史总次数
    history_friday: int    # 历史周五次数
    history_sunday: int    # 历史周日次数
    avg_total: float       # 月均次数/N月
    avg_friday: float      # 月均周五/N月
    avg_sunday: float      # 月均周日/N月


# ---------------------------------------------------------------------------
# Core loader function
# ---------------------------------------------------------------------------
def load_teacher_records(excel_path: str) -> list[TeacherRecord]:
    """
    Read the "清洗后数据" sheet from *excel_path* and return a list of
    immutable TeacherRecord instances, one per row.

    Raises:
        ValueError: if the target sheet is missing, any required column is
                    absent, the avg columns cannot be located by fuzzy match,
                    or a row contains an unresolvable value in a critical field.
    """
    # -- Read sheet ----------------------------------------------------------
    try:
        df = pd.read_excel(excel_path, sheet_name=_SHEET_NAME, dtype=str)
    except ValueError as exc:
        raise ValueError(
            f"Sheet '{_SHEET_NAME}' not found in '{excel_path}'. "
            "Run clean_schedule.py first to generate it."
        ) from exc

    # -- Static column validation --------------------------------------------
    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Sheet '{_SHEET_NAME}' is missing required columns: {missing}. "
            "The sheet may be outdated — re-run clean_schedule.py."
        )

    # -- Resolve dynamic avg column names (suffix varies with month count) ---
    def _resolve_fuzzy_col(like: str) -> str:
        matches = df.filter(like=like).columns
        if len(matches) == 0:
            raise ValueError(
                f"Sheet '{_SHEET_NAME}' has no column matching '{like}*'. "
                "Re-run clean_schedule.py to regenerate the sheet."
            )
        return matches[0]

    col_avg_total  = _resolve_fuzzy_col("月均次数")
    col_avg_friday = _resolve_fuzzy_col("月均周五")
    col_avg_sunday = _resolve_fuzzy_col("月均周日")

    # -- Row-by-row conversion -----------------------------------------------
    records: list[TeacherRecord] = []

    for row_idx, row in df.iterrows():
        excel_row = int(row_idx) + 2  # 1-based header + 0-based index

        # teacher_id
        try:
            teacher_id = int(float(row["序号"]))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Row {excel_row}: '序号' cannot be converted to int "
                f"(value={row['序号']!r})."
            ) from exc

        # name
        name = str(row[_NAME_COL]).strip()
        if not name or name.lower() == "nan":
            raise ValueError(f"Row {excel_row}: '姓名' is empty or NaN.")

        # subject / floor_zone — accept NaN as empty string
        def _str(val: object) -> str:
            s = str(val).strip()
            return "" if s.lower() == "nan" else s

        subject   = _str(row["教学学科"])
        floor_zone = _str(row["楼层"])

        # tags — split on Chinese or English comma; strip whitespace
        raw_tags = _str(row["要求"])
        if raw_tags:
            parts = raw_tags.replace("，", ",").split(",")
            tags: frozenset[str] = frozenset(p.strip() for p in parts if p.strip())
        else:
            tags = frozenset()

        # Safety interception: teacher has no floor but is not marked 不排了
        # → auto-inject the tag to prevent CP-SAT from failing to match a slot
        if not floor_zone and "不排了" not in tags:
            tags = tags | frozenset({"不排了"})

        # is_banzhuren
        is_banzhuren: bool = str(row["是否班主任"]).strip() == "是"

        # integer history columns
        def _int_col(col: str) -> int:
            val = pd.to_numeric(row[col], errors="coerce")
            return 0 if pd.isna(val) else int(val)

        history_total  = _int_col("历史总次数")
        history_friday = _int_col("历史周五次数")
        history_sunday = _int_col("历史周日次数")

        # float avg columns (dynamic names resolved above)
        def _float_col(col: str) -> float:
            val = pd.to_numeric(row[col], errors="coerce")
            return 0.0 if pd.isna(val) else float(val)

        avg_total  = _float_col(col_avg_total)
        avg_friday = _float_col(col_avg_friday)
        avg_sunday = _float_col(col_avg_sunday)

        records.append(
            TeacherRecord(
                teacher_id=teacher_id,
                name=name,
                subject=subject,
                floor_zone=floor_zone,
                tags=tags,
                is_banzhuren=is_banzhuren,
                history_total=history_total,
                history_friday=history_friday,
                history_sunday=history_sunday,
                avg_total=avg_total,
                avg_friday=avg_friday,
                avg_sunday=avg_sunday,
            )
        )

    del df  # free memory; records are immutable dataclasses
    return records


# ---------------------------------------------------------------------------
# Verification entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_EXCEL_PATH
    print(f"Loading from: {path}")
    print(f"Sheet: {_SHEET_NAME}\n")

    teacher_records = load_teacher_records(path)
    total = len(teacher_records)

    print(f"Total: {total} records\n")
    print("--- First 3 ---")
    for rec in teacher_records[:3]:
        print(rec)

    print("\n--- Last 1 ---")
    print(teacher_records[-1])
