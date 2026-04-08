# Technical Debt & TODO — DutyFlow (Degradation)

> This file tracks active technical debt and pending work items.
> Update this file whenever a debt item is introduced or resolved.
> Format: each item has a short title, date introduced, owner, and description.

---

## Active

### DEBT-001 · BANZHUREN hardcoded in clean_schedule.py
- **Introduced**: 2026-04-06
- **Description**: The 班主任 name set (16 people; 肖中海 added 2026-04-06) is hardcoded
  as a Python literal in `clean_schedule.py`. Per Golden Rule 4.1 this should ideally live
  in a config file. MISSING_TEACHERS was removed 2026-04-07 (step 0 workflow: user now
  manually maintains the "次数" sheet directly).
- **Impact**: Low — changes rarely; editing the script is acceptable for now.
- **Resolution**: Move to `data_config.yaml` when the list changes frequently.

### DEBT-002 · 楼层 / 年级 still empty for 余海雷 and 王詹航
- **Introduced**: 2026-04-06
- **Description**: `余海雷` and `王詹航` have `要求=不排了` but their 楼层 and 年级
  fields remain `None` in the "次数" sheet. This is acceptable for scheduling (they won't
  be assigned), but the roster is incomplete.
- **Impact**: None for solver correctness; cosmetic.
- **Resolution**: Fill in when floor/grade info becomes known.

---

## Completed

### DONE-006 · 学科/星期偏好权重偏低 + 班主任学科加分未屏蔽
- **Completed**: 2026-04-08
- **Description**: `pref_english_mon_thu / pref_chinese_tue / pref_politics_wed` 由 50 提升至 200，
  使学科偏好权重(200) > 偏差惩罚(80)，政治老师优先出现在周三。
  同步修复隐性 bug：班主任教师原本也会获得学科/星期加分，导致提权后 SC-4(-200) 被学科加分(+200) 抵消，
  蒋寅被排两次。修复方案：在三个学科偏好条件前加 `not t.is_banzhuren` 判断，落实"班主任标签优先于学科标签"。
  求解时限同步调整 300s → 210s。

### DONE-005 · 真实日历时间轴 + 月份自动衔接 + 特殊日期支持
- **Completed**: 2026-04-07
- **Description**: 引入 `build_schedule_days()` 真实日历函数；新增 `scheduling_state.json` 和 `special_dates.json`；
  `main.py` 完整编排器实现；`clean_schedule.py` 删除补录逻辑，新增日期列兼容与状态同步；
  输出 sheet 改为"YYYY年M月排班（暂定）"。求解时限 60s → 180s → 300s。

### DONE-004 · 班主任有概率被排两次（求解器次优部分）
- **Completed**: 2026-04-07
- **Description**: 增加 SC-4（`penalty_bz_non_weekend: -200`）使班主任出现在周一至周四的净
  得分为负，求解器主动回避，修复了蒋寅（1楼）被排周四的次优解问题。
  SC-5（`penalty_non_bz_weekend_double: -150`）同步落地，非班主任周末+双次惩罚。
  **结构性残留**：2-3楼 7 名班主任 × 1 次 = 7 槽，但 8 名非班主任满载后仍需 8 班主任槽，
  叶云必须排 2 次属数学约束而非求解器问题。开发者将通过调整楼层分配解决。

### DONE-002 · 核心算子重构 — HC-6 range constraints + soft terms + "test" output sheet
- **Completed**: 2026-04-06
- **Description**: Added HC-6 极差 hard constraints (new-assignment range ≤ 1 per group per
  dimension); implemented pref_spacing_gap, pref_non_banzhuren_double, and penalty_avg_deviation
  soft terms; renamed output sheet from "排班结果" to "test" (also excluded from duty-count scan).
  Solver time limit raised from 30 s → 60 s to accommodate increased model complexity.
  Note: HC-6 applies to *new* assignments only (not projected historical totals) because the
  existing historical data already has imbalances up to range=11 in non-BZ total, which cannot
  be corrected in a single scheduling cycle.

### DONE-003 · 真实日历时间轴 + 月份自动衔接 + 特殊日期支持
- **Completed**: 2026-04-07
- **Description**: 引入 `build_schedule_days()` 日历函数，poc_solver 改为真实日历枚举；
  新增 `scheduling_state.json`（月份状态文件）和 `special_dates.json`（节假日/调休/全体班主任日配置）；
  `main.py` 实现完整编排器；`clean_schedule.py` 删除补录逻辑，增加"日期"列兼容和动态 sheet 排除。
  输出 sheet 命名为"X月排班（暂定）"，用户确认后手动改名归档。

### DONE-001 · 晚自修排版.xlsx data cleaning (clean_schedule.py)
- **Completed**: 2026-04-06
- **Description**: Implemented `clean_schedule.py` to normalize floors, add 5 missing
  teachers, tag 班主任 via 是否班主任 column, and generate "清洗后数据" sheet with
  historical duty counts (total / 周五 / 周日 / monthly averages) across all 8 months.
