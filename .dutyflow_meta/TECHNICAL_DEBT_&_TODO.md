# Technical Debt & TODO — DutyFlow (Degradation)

> This file tracks active technical debt and pending work items.
> Update this file whenever a debt item is introduced or resolved.
> Format: each item has a short title, date introduced, owner, and description.

---

## Active

### DEBT-001 · BANZHUREN / MISSING_TEACHERS hardcoded in clean_schedule.py
- **Introduced**: 2026-04-06
- **Description**: The 班主任 name set (15 people) and the 5 supplemental teacher records
  are hardcoded as Python literals in `clean_schedule.py`. Per Golden Rule 4.1 these
  configuration values should ideally live in a config file (e.g., `PARAMS_REGISTRY.yaml`
  or a dedicated `data_config.yaml`) so they can be updated without touching source code.
- **Impact**: Low — these change rarely; editing the script is acceptable for now.
- **Resolution**: Move to `data_config.yaml` when a second maintainer joins or when
  the list changes frequently.

### DEBT-002 · 楼层 / 年级 still empty for 余海雷 and 王詹航
- **Introduced**: 2026-04-06
- **Description**: `余海雷` and `王詹航` have `要求=不排了` but their 楼层 and 年级
  fields remain `None` in the "次数" sheet. This is acceptable for scheduling (they won't
  be assigned), but the roster is incomplete.
- **Impact**: None for solver correctness; cosmetic.
- **Resolution**: Fill in when floor/grade info becomes known.

---

## Completed

### DONE-001 · 晚自修排版.xlsx data cleaning (clean_schedule.py)
- **Completed**: 2026-04-06
- **Description**: Implemented `clean_schedule.py` to normalize floors, add 5 missing
  teachers, tag 班主任 via 是否班主任 column, and generate "清洗后数据" sheet with
  historical duty counts (total / 周五 / 周日 / monthly averages) across all 8 months.
