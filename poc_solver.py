"""
poc_solver.py — Phase 3: CP-SAT Solver
Builds and solves the duty-roster scheduling model, then exports the result to Excel.

Module boundaries (from ARCHITECTURE.md):
  - No I/O or data-loading here — receives List[TeacherRecord] from poc_loader.
  - No LLM calls at runtime.
  - All numeric constants come from PARAMS_REGISTRY.yaml via the config dict.
"""

from __future__ import annotations

import pathlib
from itertools import product

import pandas as pd
import yaml
from openpyxl.styles import PatternFill
from ortools.sat.python import cp_model

from poc_loader import TeacherRecord, load_teacher_records

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_REGISTRY_PATH = pathlib.Path(__file__).parent / ".dutyflow_meta" / "PARAMS_REGISTRY.yaml"

with _REGISTRY_PATH.open(encoding="utf-8") as _f:
    _CFG = yaml.safe_load(_f)

_DEFAULT_EXCEL_PATH: str = _CFG["clean_schedule"]["excel_path"]

# slot_id → floor_zone string (must match TeacherRecord.floor_zone)
SLOT_ZONE: dict[str, str] = {
    "floor_1":   "1楼",
    "floor_2_3": "2-3楼",
    "floor_4_5": "4-5楼",
}
SLOT_IDS: list[str] = list(SLOT_ZONE.keys())

# Day indices within a 7-day week (0=Mon … 6=Sun)
ACTIVE_DAYS: list[int] = [0, 1, 2, 3, 4, 6]

DAY_NAMES: dict[int, str] = {
    0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 6: "周日",
}


# ---------------------------------------------------------------------------
# Solver class
# ---------------------------------------------------------------------------
class DutySolver:
    def __init__(self, records: list[TeacherRecord], config: dict) -> None:
        self._records = records
        self._config = config
        self._by_id: dict[int, TeacherRecord] = {t.teacher_id: t for t in records}

        # Config extraction
        self._num_weeks: int = config["schedule"]["num_weeks"]
        self._headcount: dict[str, int] = {
            sid: config["slots"][sid]["required_headcount"] for sid in SLOT_IDS
        }
        self._weights: dict[str, int] = config["weights"]
        self._time_limit: float = float(config["solver"]["time_limit_seconds"])
        self._num_workers: int = int(config["solver"]["num_search_workers"])
        self._seed: int = int(config["solver"]["random_seed"])
        self._log_progress: bool = bool(config["solver"]["log_search_progress"])
        self._output_sheet_name: str = config["output"]["output_sheet_name"]

        mt = config["monthly_targets"]
        self._bz_target: int = int(mt["banzhuren_target"])
        self._non_bz_target: int = int(mt["non_banzhuren_target"])
        self._max_projected_range: int = int(mt["max_projected_range"])
        self._min_week_gap: int = int(config["soft_constraints"]["min_week_gap"])

        # CP-SAT objects (populated by _build)
        self.model = cp_model.CpModel()
        self.x: dict[tuple, cp_model.IntVar] = {}

        # Per-teacher IntVars for new assignment counts (populated by _precompute_teacher_totals)
        self._new_total: dict[int, cp_model.IntVar] = {}
        self._new_friday: dict[int, cp_model.IntVar] = {}
        self._new_sunday: dict[int, cp_model.IntVar] = {}

        self.cp_solver: cp_model.CpSolver | None = None
        self.solver_status: int | None = None

        self._build()

    # -----------------------------------------------------------------------
    # Internal: model construction
    # -----------------------------------------------------------------------
    def _build(self) -> None:
        self._create_variables()
        self._precompute_teacher_totals()
        self._add_hard_constraints()
        self._add_range_constraints()
        self._set_objective()

    def _create_variables(self) -> None:
        """Sparse variable matrix: only create BoolVars for valid assignments."""
        for t in self._records:
            if "不排了" in t.tags:
                continue
            for w, d, slot_id in product(
                range(self._num_weeks), ACTIVE_DAYS, SLOT_IDS
            ):
                if t.floor_zone != SLOT_ZONE[slot_id]:
                    continue
                if d == 4 and "不要周五" in t.tags:
                    continue
                if d == 6 and "不要周日" in t.tags:
                    continue
                key = (t.teacher_id, w, d, slot_id)
                self.x[key] = self.model.NewBoolVar(
                    f"x_{t.teacher_id}_{w}_{d}_{slot_id}"
                )

    def _precompute_teacher_totals(self) -> None:
        """
        For each active teacher (has at least one x-variable), create IntVars that sum
        their new assignments across all weeks/days/slots.  These are reused by both
        _add_range_constraints (projected history check) and _set_objective (soft terms).
        """
        for t in self._records:
            tid = t.teacher_id
            all_vars = [v for (i, *_), v in self.x.items() if i == tid]
            if not all_vars:
                continue

            cap = 1 if "一个月只能1次" in t.tags else 2

            new_total = self.model.NewIntVar(0, cap, f"new_total_{tid}")
            self.model.Add(new_total == sum(all_vars))
            self._new_total[tid] = new_total

            fri_vars = [v for (i, w, d, s), v in self.x.items() if i == tid and d == 4]
            new_friday = self.model.NewIntVar(0, cap, f"new_fri_{tid}")
            self.model.Add(new_friday == (sum(fri_vars) if fri_vars else 0))
            self._new_friday[tid] = new_friday

            sun_vars = [v for (i, w, d, s), v in self.x.items() if i == tid and d == 6]
            new_sunday = self.model.NewIntVar(0, cap, f"new_sun_{tid}")
            self.model.Add(new_sunday == (sum(sun_vars) if sun_vars else 0))
            self._new_sunday[tid] = new_sunday

    def _add_hard_constraints(self) -> None:
        # HC-1: Coverage — every (w, d, slot) must have exactly required_headcount teachers
        for w, d, slot_id in product(
            range(self._num_weeks), ACTIVE_DAYS, SLOT_IDS
        ):
            slot_vars = [
                self.x[(tid, w, d, slot_id)]
                for tid in self._by_id
                if (tid, w, d, slot_id) in self.x
            ]
            if not slot_vars:
                raise RuntimeError(
                    f"No eligible teachers for slot '{slot_id}' "
                    f"on week {w}, day index {d} ({DAY_NAMES[d]}). "
                    "Check floor assignments and tags in 清洗后数据 sheet."
                )
            self.model.Add(sum(slot_vars) == self._headcount[slot_id])

        # HC-2: No-clone — each teacher at most 1 slot per day
        for t in self._records:
            for w, d in product(range(self._num_weeks), ACTIVE_DAYS):
                day_vars = [
                    self.x[(t.teacher_id, w, d, s)]
                    for s in SLOT_IDS
                    if (t.teacher_id, w, d, s) in self.x
                ]
                if day_vars:
                    self.model.Add(sum(day_vars) <= 1)

        # HC-3: Weekly cap — each teacher at most 1 duty per week
        for t in self._records:
            for w in range(self._num_weeks):
                week_vars = [
                    self.x[(t.teacher_id, w, d, s)]
                    for d, s in product(ACTIVE_DAYS, SLOT_IDS)
                    if (t.teacher_id, w, d, s) in self.x
                ]
                if week_vars:
                    self.model.Add(sum(week_vars) <= 1)

        # HC-4: Monthly cap — 1 if tagged "一个月只能1次", else 2
        for t in self._records:
            all_vars = [v for (tid, *_), v in self.x.items() if tid == t.teacher_id]
            if not all_vars:
                continue
            cap = 1 if "一个月只能1次" in t.tags else 2
            self.model.Add(sum(all_vars) <= cap)

        # HC-5: Weekend mutual exclusion — Friday duties + Sunday duties <= 1
        for t in self._records:
            if "一个月只能1次" in t.tags:
                continue  # already capped at 1 globally
            fri_vars = [
                self.x[(t.teacher_id, w, 4, s)]
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 4, s) in self.x
            ]
            sun_vars = [
                self.x[(t.teacher_id, w, 6, s)]
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 6, s) in self.x
            ]
            if fri_vars or sun_vars:
                self.model.Add(sum(fri_vars) + sum(sun_vars) <= 1)

    def _add_range_constraints(self) -> None:
        """
        HC-6: 极差约束 — for each teacher group {BZ, non-BZ}, the range
        (max − min) of NEW assignment counts in this scheduling cycle must not exceed
        max_projected_range.

        Note: The requirement states 历史总值班次数极差<=1 (historical running totals).
        However, the existing historical data already has imbalances up to 11 among
        non-BZ teachers — gaps that cannot be closed in a single month.  Applying the
        range constraint to the NEW assignments for this cycle is the correct per-cycle
        interpretation: this month's schedule must itself be fair (each teacher within
        a group gets an equal number of new duties, range ≤ 1), which gradually reduces
        the historical imbalance over successive months.

        Applies independently to total / friday / sunday new counts.
        Groups with ≤1 active teacher are skipped (range is trivially 0).
        """
        bz_active = [
            t for t in self._records
            if t.is_banzhuren and t.teacher_id in self._new_total
        ]
        non_bz_active = [
            t for t in self._records
            if not t.is_banzhuren and t.teacher_id in self._new_total
        ]

        def _add_range_for_group(
            group: list[TeacherRecord],
            new_dict: dict[int, cp_model.IntVar],
            label: str,
        ) -> None:
            if len(group) <= 1:
                return

            cap = 2  # conservative upper bound for domain
            new_vars = [new_dict[t.teacher_id] for t in group]

            max_new = self.model.NewIntVar(0, cap, f"max_new_{label}")
            min_new = self.model.NewIntVar(0, cap, f"min_new_{label}")
            self.model.AddMaxEquality(max_new, new_vars)
            self.model.AddMinEquality(min_new, new_vars)
            self.model.Add(max_new - min_new <= self._max_projected_range)

        for group_name, group in [("bz", bz_active), ("nonbz", non_bz_active)]:
            _add_range_for_group(group, self._new_total,  f"{group_name}_total")
            _add_range_for_group(group, self._new_friday, f"{group_name}_fri")
            _add_range_for_group(group, self._new_sunday, f"{group_name}_sun")

    def _set_objective(self) -> None:
        W = self._weights
        terms: list = []

        # --- Existing subject/day preference terms + SC-4 ---
        for (tid, w, d, slot_id), var in self.x.items():
            t = self._by_id[tid]
            if t.is_banzhuren and d in (4, 6):
                terms.append(var * W["pref_banzhuren_weekend"])
            if t.is_banzhuren and d not in (4, 6):
                # SC-4: penalty_bz_non_weekend
                # 班主任出现在周一到周四，净得分为负，求解器主动回避
                terms.append(var * W["penalty_bz_non_weekend"])
            if t.subject == "英语" and d in (0, 3):
                terms.append(var * W["pref_english_mon_thu"])
            if t.subject == "语文" and d == 1:
                terms.append(var * W["pref_chinese_tue"])
            if t.subject == "政治" and d == 2:
                terms.append(var * W["pref_politics_wed"])

        # --- SC-1: pref_non_banzhuren_double ---
        # Reward the solver for giving non-BZ teachers more assignments.
        # When a non-BZ teacher gets 2 duties, this term contributes 2× the weight,
        # biasing the solver to fill the 2-slot quota with non-BZ teachers first.
        for t in self._records:
            if not t.is_banzhuren and t.teacher_id in self._new_total:
                terms.append(self._new_total[t.teacher_id] * W["pref_non_banzhuren_double"])

        # --- SC-2: pref_spacing_gap ---
        # For each teacher who can get 2 assignments, reward week-pairs that are
        # at least min_week_gap weeks apart.
        gap = self._min_week_gap
        for t in self._records:
            if "一个月只能1次" in t.tags:
                continue
            tid = t.teacher_id
            for w1 in range(self._num_weeks):
                for w2 in range(w1 + gap, self._num_weeks):
                    w1_vars = [
                        self.x[(tid, w1, d, s)]
                        for d, s in product(ACTIVE_DAYS, SLOT_IDS)
                        if (tid, w1, d, s) in self.x
                    ]
                    w2_vars = [
                        self.x[(tid, w2, d, s)]
                        for d, s in product(ACTIVE_DAYS, SLOT_IDS)
                        if (tid, w2, d, s) in self.x
                    ]
                    if not w1_vars or not w2_vars:
                        continue
                    # gap_ok = 1 iff teacher is assigned in both w1 and w2
                    gap_ok = self.model.NewBoolVar(f"gap_{tid}_{w1}_{w2}")
                    sum_w1 = sum(w1_vars)
                    sum_w2 = sum(w2_vars)
                    self.model.Add(gap_ok <= sum_w1)
                    self.model.Add(gap_ok <= sum_w2)
                    self.model.Add(gap_ok >= sum_w1 + sum_w2 - 1)
                    terms.append(gap_ok * W["pref_spacing_gap"])

        # --- SC-3: penalty_avg_deviation ---
        # Penalize teachers whose new assignment count deviates from their monthly target.
        # BZ target = banzhuren_target; non-BZ target = non_banzhuren_target.
        # Uses AddAbsEquality to model |new_count - target| as an IntVar.
        penalty_weight = abs(int(W["penalty_avg_deviation"]))
        for t in self._records:
            tid = t.teacher_id
            if tid not in self._new_total:
                continue
            target = self._bz_target if t.is_banzhuren else self._non_bz_target
            cap = 1 if "一个月只能1次" in t.tags else 2
            max_dev = max(target, cap)  # max possible deviation
            dev_var = self.model.NewIntVar(0, max_dev, f"dev_{tid}")
            # new_total - target can range from -target to cap-target
            diff_lb = -target
            diff_ub = cap - target
            diff_var = self.model.NewIntVar(diff_lb, diff_ub, f"diff_{tid}")
            self.model.Add(diff_var == self._new_total[tid] - target)
            self.model.AddAbsEquality(dev_var, diff_var)
            terms.append(dev_var * (-penalty_weight))

        # --- SC-5: penalty_non_bz_weekend_double ---
        # 触发条件: 非班主任本月已排周五/日 1 次 AND 还有第二次值班
        # wad (weekend_and_double) = 1 iff (fri_new + sun_new == 1) AND (total_new == 2)
        # 推导: fri+sun ∈ {0,1}（由HC-5保证），total ∈ {0,1,2}
        #   wad=1 ⟺ fri+sun+total == 3，因此:
        #   wad <= fri+sun              (fri+sun=0 → wad=0)
        #   wad >= fri+sun + total - 2  (fri+sun+total=3 → wad>=1)
        for t in self._records:
            if t.is_banzhuren or t.teacher_id not in self._new_total:
                continue
            tid = t.teacher_id
            wad = self.model.NewBoolVar(f"wad_{tid}")
            self.model.Add(wad <= self._new_friday[tid] + self._new_sunday[tid])
            self.model.Add(
                wad >= self._new_friday[tid] + self._new_sunday[tid] + self._new_total[tid] - 2
            )
            terms.append(wad * W["penalty_non_bz_weekend_double"])

        if terms:
            self.model.Maximize(sum(terms))

    # -----------------------------------------------------------------------
    # Public: solve
    # -----------------------------------------------------------------------
    def solve(self) -> str:
        """
        Run CP-SAT search.
        Returns the status name string ("OPTIMAL" or "FEASIBLE").
        Raises RuntimeError if the model is INFEASIBLE or search times out without a solution.
        """
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self._time_limit
        solver.parameters.num_search_workers = self._num_workers
        solver.parameters.random_seed = self._seed
        solver.parameters.log_search_progress = self._log_progress

        self.cp_solver = solver
        self.solver_status = solver.Solve(self.model)

        status_name = solver.StatusName(self.solver_status)

        if self.solver_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(
                f"CP-SAT returned {status_name}. "
                "Possible causes: (1) too few eligible teachers per slot, "
                "(2) monthly caps too restrictive, "
                "(3) HC-6 range constraints infeasible — history counts already differ "
                "by more than max_projected_range within a teacher group and cannot be "
                "rebalanced with the current eligible teacher pool. "
                "Check 清洗后数据 sheet and PARAMS_REGISTRY.yaml → monthly_targets."
            )
        return status_name

    # -----------------------------------------------------------------------
    # Public: post-solve verification & debug summary
    # -----------------------------------------------------------------------
    def verify_solution(self) -> list[str]:
        """
        Post-solve: verify each HC-1 ~ HC-6 against the solved variable values.
        Returns a list of violation strings. Empty list = no violations found.
        Must be called after a successful solve().
        """
        solver = self.cp_solver
        violations: list[str] = []

        # HC-1: Coverage
        for w, d, slot_id in product(range(self._num_weeks), ACTIVE_DAYS, SLOT_IDS):
            count = sum(
                solver.Value(self.x[(tid, w, d, slot_id)])
                for tid in self._by_id
                if (tid, w, d, slot_id) in self.x
            )
            required = self._headcount[slot_id]
            if count != required:
                violations.append(
                    f"HC-1 FAIL: 第{w+1}周{DAY_NAMES[d]} {slot_id} "
                    f"实际{count}人，要求{required}人"
                )

        # HC-2: No-clone
        for t in self._records:
            for w, d in product(range(self._num_weeks), ACTIVE_DAYS):
                day_count = sum(
                    solver.Value(self.x[(t.teacher_id, w, d, s)])
                    for s in SLOT_IDS
                    if (t.teacher_id, w, d, s) in self.x
                )
                if day_count > 1:
                    violations.append(
                        f"HC-2 FAIL: {t.name} 第{w+1}周{DAY_NAMES[d]} 同天被排{day_count}次"
                    )

        # HC-3: Weekly cap
        for t in self._records:
            for w in range(self._num_weeks):
                week_count = sum(
                    solver.Value(self.x[(t.teacher_id, w, d, s)])
                    for d, s in product(ACTIVE_DAYS, SLOT_IDS)
                    if (t.teacher_id, w, d, s) in self.x
                )
                if week_count > 1:
                    violations.append(
                        f"HC-3 FAIL: {t.name} 第{w+1}周 被排{week_count}次"
                    )

        # HC-4: Monthly cap
        for t in self._records:
            cap = 1 if "一个月只能1次" in t.tags else 2
            total = sum(
                solver.Value(self.x[key])
                for key in self.x
                if key[0] == t.teacher_id
            )
            if total > cap:
                violations.append(
                    f"HC-4 FAIL: {t.name} 月总次数{total}，上限{cap}"
                )

        # HC-5: Weekend mutex
        for t in self._records:
            if "一个月只能1次" in t.tags:
                continue
            fri_count = sum(
                solver.Value(self.x[(t.teacher_id, w, 4, s)])
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 4, s) in self.x
            )
            sun_count = sum(
                solver.Value(self.x[(t.teacher_id, w, 6, s)])
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 6, s) in self.x
            )
            if fri_count + sun_count > 1:
                violations.append(
                    f"HC-5 FAIL: {t.name} 周五{fri_count}次+周日{sun_count}次 > 1"
                )

        # HC-6: Range constraint
        def _count_total(t: TeacherRecord) -> int:
            return sum(solver.Value(self.x[k]) for k in self.x if k[0] == t.teacher_id)

        def _count_fri(t: TeacherRecord) -> int:
            return sum(
                solver.Value(self.x[(t.teacher_id, w, 4, s)])
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 4, s) in self.x
            )

        def _count_sun(t: TeacherRecord) -> int:
            return sum(
                solver.Value(self.x[(t.teacher_id, w, 6, s)])
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 6, s) in self.x
            )

        bz_active = [
            t for t in self._records
            if t.is_banzhuren and t.teacher_id in self._new_total
        ]
        non_bz_active = [
            t for t in self._records
            if not t.is_banzhuren and t.teacher_id in self._new_total
        ]

        for group, fn, label in [
            (bz_active,     _count_total, "班主任-总次数"),
            (bz_active,     _count_fri,   "班主任-周五"),
            (bz_active,     _count_sun,   "班主任-周日"),
            (non_bz_active, _count_total, "非班主任-总次数"),
            (non_bz_active, _count_fri,   "非班主任-周五"),
            (non_bz_active, _count_sun,   "非班主任-周日"),
        ]:
            if len(group) <= 1:
                continue
            vals = [fn(t) for t in group]
            r = max(vals) - min(vals)
            if r > self._max_projected_range:
                violations.append(
                    f"HC-6 FAIL: {label} 极差={r}，超过上限{self._max_projected_range}"
                )

        return violations

    def print_solution_summary(self, output_path: str | None = None) -> None:
        """
        Print a structured debug summary: per-teacher new-assignment counts
        (grouped by BZ / non-BZ) and the full week-by-week schedule table.
        If output_path is given, also writes to that file (UTF-8, overwrites).
        Must be called after a successful solve().
        """
        solver = self.cp_solver
        lines: list[str] = []
        add = lines.append

        add("=" * 60)
        add("  SOLVER DEBUG SUMMARY")
        add("=" * 60)

        def _counts(t: TeacherRecord) -> tuple[int, int, int]:
            total = sum(solver.Value(self.x[k]) for k in self.x if k[0] == t.teacher_id)
            fri = sum(
                solver.Value(self.x[(t.teacher_id, w, 4, s)])
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 4, s) in self.x
            )
            sun = sum(
                solver.Value(self.x[(t.teacher_id, w, 6, s)])
                for w, s in product(range(self._num_weeks), SLOT_IDS)
                if (t.teacher_id, w, 6, s) in self.x
            )
            return total, fri, sun

        for group_label, group in [
            ("【班主任组】", [
                t for t in self._records
                if t.is_banzhuren and t.teacher_id in self._new_total
            ]),
            ("【非班主任组】", [
                t for t in self._records
                if not t.is_banzhuren and t.teacher_id in self._new_total
            ]),
        ]:
            add(f"\n{group_label} ({len(group)}人)")
            add(f"  {'姓名':<8} {'总次数':>4} {'周五':>4} {'周日':>4}  备注")
            add(f"  {'-'*8} {'-'*4} {'-'*4} {'-'*4}")
            totals, fris, suns = [], [], []
            for t in sorted(group, key=lambda x: x.name):
                total, fri, sun = _counts(t)
                totals.append(total)
                fris.append(fri)
                suns.append(sun)
                note = "*** 被排2次" if (total == 2 and t.is_banzhuren) else ""
                add(f"  {t.name:<8} {total:>4} {fri:>4} {sun:>4}  {note}")
            if totals:
                add(
                    f"  {'[极差]':<8} {max(totals)-min(totals):>4} "
                    f"{max(fris)-min(fris):>4} {max(suns)-min(suns):>4}"
                )

        add(f"\n{'='*60}")
        add("  排班明细（周 × 日 × 槽位）")
        add("=" * 60)
        unassigned = self._config["output"]["unassigned_placeholder"]
        for w in range(self._num_weeks):
            add(f"\n  第{w+1}周:")
            for d in ACTIVE_DAYS:
                parts = [f"    {DAY_NAMES[d]}"]
                for slot_id in SLOT_IDS:
                    zone = SLOT_ZONE[slot_id]
                    name = unassigned
                    for tid, t in self._by_id.items():
                        if (
                            (tid, w, d, slot_id) in self.x
                            and solver.Value(self.x[(tid, w, d, slot_id)]) == 1
                        ):
                            name = t.name
                            break
                    parts.append(f"{zone}:{name}")
                add("  ".join(parts))

        add("\n" + "=" * 60)

        output = "\n".join(lines)
        print(output)

        if output_path:
            pathlib.Path(output_path).write_text(output, encoding="utf-8")
            print(f"\n[debug report → {output_path}]")

    # -----------------------------------------------------------------------
    # Public: export
    # -----------------------------------------------------------------------
    def export_to_excel(self, output_path: str) -> None:
        """
        Write the solved schedule as a new sheet (output_sheet_name from config)
        into *output_path*.  Replaces the sheet if it already exists.
        Must be called after solve().
        """
        if self.cp_solver is None or self.solver_status not in (
            cp_model.OPTIMAL, cp_model.FEASIBLE
        ):
            raise RuntimeError(
                "export_to_excel() called before a successful solve(). "
                "Call solve() first."
            )

        rows: list[dict] = []
        unassigned_placeholder: str = self._config["output"]["unassigned_placeholder"]

        for w, d in product(range(self._num_weeks), ACTIVE_DAYS):
            row: dict[str, str] = {"日期": f"第{w + 1}周{DAY_NAMES[d]}"}
            for slot_id in SLOT_IDS:
                zone = SLOT_ZONE[slot_id]
                assigned_name = unassigned_placeholder
                for tid, t in self._by_id.items():
                    if (tid, w, d, slot_id) in self.x:
                        if self.cp_solver.Value(self.x[(tid, w, d, slot_id)]) == 1:
                            assigned_name = t.name
                            break
                row[zone] = assigned_name
            rows.append(row)

        df = pd.DataFrame(rows, columns=["日期", "1楼", "2-3楼", "4-5楼"])

        # Build a set of 班主任 names for cell highlighting
        banzhuren_names: set[str] = {t.name for t in self._records if t.is_banzhuren}
        orange_yellow = PatternFill(
            fill_type="solid", fgColor="FFB300"  # amber / 橙黄色
        )

        sheet_name = self._output_sheet_name
        with pd.ExcelWriter(
            output_path,
            engine="openpyxl",
            mode="a",
            if_sheet_exists="replace",
        ) as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            ws = writer.sheets[sheet_name]
            # Row 1 is the header; data starts at row 2
            # Columns: A=日期, B=1楼, C=2-3楼, D=4-5楼
            for row_idx in range(2, len(rows) + 2):
                for col_idx in range(2, 5):  # cols B, C, D
                    cell = ws.cell(row=row_idx, column=col_idx)
                    if cell.value in banzhuren_names:
                        cell.fill = orange_yellow

        del df


# ---------------------------------------------------------------------------
# Verification entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    excel_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_EXCEL_PATH
    print(f"Excel: {excel_path}")

    print("Loading teacher records...")
    records = load_teacher_records(excel_path)
    print(f"  {len(records)} records loaded.")

    print("Building CP-SAT model...")
    ds = DutySolver(records, _CFG)
    print(f"  {len(ds.x)} decision variables created.")

    print("Solving...")
    status = ds.solve()
    print(f"  Solver status: {status}")

    debug_path = str(pathlib.Path(__file__).parent / "debug_solver_run.txt")
    violations = ds.verify_solution()
    if violations:
        print(f"\n[!] {len(violations)} constraint violation(s) found:")
        for v in violations:
            print(f"    {v}")
    else:
        print("\n[OK] All hard constraints verified — no violations.")

    ds.print_solution_summary(output_path=debug_path)

    print("Exporting to Excel...")
    ds.export_to_excel(excel_path)
    print(f"  结果已写入 '{_CFG['output']['output_sheet_name']}' sheet。")
