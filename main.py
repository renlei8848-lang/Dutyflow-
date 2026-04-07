"""
main.py — 排班主程序（编排器）
════════════════════════════════════════

【核心功能】
  自动推算本次应生成的排班月份，调用求解器计算最优排班方案，
  并将结果以"YYYY年M月排班（暂定）"为 sheet 名写入 Excel 文件。

【核心逻辑】
  1. 读取 scheduling_state.json → 取 last_generated，加一个月得到目标月
  2. 读取 special_dates.json → 提取目标月的特殊日期配置（节假日/调休/全体班主任日）
  3. 读取"清洗后数据"sheet → 构建 List[TeacherRecord]（教师历史数据）
  4. 构建 CP-SAT 模型：
       · 用真实日历枚举目标月的所有值班日（剔除节假日，加入调休周六）
       · 应用6条硬约束（覆盖率、不重排、周次上限、月次上限、周末互斥、极差均衡）
       · 应用5条软约束（学科/日期偏好、间隔奖励、非班主任多排奖励、偏差惩罚等）
  5. 求解 → 验证所有硬约束 → 打印摘要 → 写入 Excel
  6. 不修改 scheduling_state.json（状态由 clean_schedule.py 归档时更新）

【使用方法】
  1.（如有需要）在 special_dates.json 中填写目标月的特殊日期
  2. 打开终端，运行：
       python main.py
     或指定 Excel 路径：
       python main.py "C:/path/to/晚自修排版.xlsx"
  3. 求解完成后在 Excel 中核查"2026年5月排班（暂定）"sheet
  4. 确认无误 → 在 Excel 中将该 sheet 改名为"2026年5月"
  5. 运行 clean_schedule.py 完成归档
"""

import json
import pathlib
import sys

import yaml

from poc_loader import load_teacher_records
from poc_solver import DutySolver, _next_month

_PROJECT_ROOT = pathlib.Path(__file__).parent
_REGISTRY_PATH = _PROJECT_ROOT / ".dutyflow_meta" / "PARAMS_REGISTRY.yaml"
_STATE_PATH = _PROJECT_ROOT / "scheduling_state.json"
_SPECIAL_DATES_PATH = _PROJECT_ROOT / "special_dates.json"


def main() -> None:
    # 1. Load config
    with _REGISTRY_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    excel_path = sys.argv[1] if len(sys.argv) > 1 else config["clean_schedule"]["excel_path"]

    # 2. Read state → determine target month
    if not _STATE_PATH.exists():
        print("[!] scheduling_state.json 不存在，请先创建该文件。")
        print('    示例: {"last_generated": "2026-04", "generated_months": ["2026-03", "2026-04"]}')
        sys.exit(1)

    state = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    target_month = _next_month(state["last_generated"])
    print(f"=== DutyFlow — 目标排班月：{target_month} ===\n")

    # 3. Load special dates for this month
    special_dates_for_month: dict = {}
    if _SPECIAL_DATES_PATH.exists():
        all_special = json.loads(_SPECIAL_DATES_PATH.read_text(encoding="utf-8"))
        cleaned = {k: v for k, v in all_special.items() if not k.startswith("_")}
        special_dates_for_month = cleaned.get(target_month, {})
        if special_dates_for_month:
            notes = special_dates_for_month.get("notes", "（无备注）")
            print(f"特殊日期配置已加载：{notes}")
            holidays = special_dates_for_month.get("holiday_ranges", [])
            extra = special_dates_for_month.get("extra_workdays", [])
            bz_days = special_dates_for_month.get("all_bz_required_days", [])
            if holidays:
                print(f"  节假日区间：{holidays}")
            if extra:
                print(f"  调休工作日：{extra}")
            if bz_days:
                print(f"  全体班主任日：{bz_days}")
        else:
            print(f"special_dates.json 中无 {target_month} 配置，使用标准日历。")
    else:
        print("未找到 special_dates.json，使用标准日历。")

    # 4. Load teacher records
    print(f"\n正在读取教师数据：{excel_path}")
    records = load_teacher_records(excel_path)
    print(f"  已加载 {len(records)} 位教师。")

    # 5. Build CP-SAT model
    print("\n正在构建 CP-SAT 模型...")
    ds = DutySolver(records, config, target_month, special_dates_for_month)
    print(
        f"  值班日：{len(ds._schedule_days)} 天  |  "
        f"周次：{ds._num_weeks}  |  "
        f"决策变量：{len(ds.x)}"
    )

    # 6. Solve
    print("\n求解中（最长等待时间见 PARAMS_REGISTRY.yaml → solver.time_limit_seconds）...")
    try:
        status = ds.solve()
    except RuntimeError as e:
        print(f"\n[!] 求解失败：{e}")
        print("scheduling_state.json 未更新，请检查约束后重试。")
        sys.exit(1)

    print(f"  求解状态：{status}")

    # 7. Verify hard constraints
    violations = ds.verify_solution()
    if violations:
        print(f"\n[!] 发现 {len(violations)} 个硬约束违规：")
        for v in violations:
            print(f"    {v}")
        print("scheduling_state.json 未更新，请检查。")
        sys.exit(1)
    print("  [OK] 所有硬约束验证通过。")

    # 8. Print debug summary
    debug_path = str(_PROJECT_ROOT / "debug_solver_run.txt")
    ds.print_solution_summary(output_path=debug_path)

    # 9. Export to Excel
    print(f"\n正在写入 Excel...")
    ds.export_to_excel(excel_path)
    print(f"  已写入 sheet：'{ds._output_sheet_name}'")

    # Derive the expected archive name from target_month ("YYYY-MM" → "YYYY年M月")
    year_str, month_str = target_month.split("-")
    archive_name = f"{year_str}年{int(month_str)}月"

    print(f"\n=== 完成！===")
    print(f"  请在 Excel 中核查 '{ds._output_sheet_name}' sheet。")
    print(f"  确认无误后，将 sheet 重命名为 '{archive_name}'，再运行 clean_schedule.py 归档。")
    print(f"  （scheduling_state.json 将由 clean_schedule.py 在归档时自动更新）")


if __name__ == "__main__":
    main()
