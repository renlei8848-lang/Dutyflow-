# DutyFlow (Degradation) — System Architecture

> Audience: Claude Code (AI). For human-readable Chinese version, see `.dutyflow_meta（中文for开发者）/ARCHITECTURE.md`.
> Last updated: 2026-04-06

---

## Design Principle

White-box, hardcoded, linear single-pass pipeline.
No abstraction layers. No LLM at runtime. No dynamic rule parsing.
The goal is to prove CP-SAT can solve this specific school's scheduling constraints,
not to build a reusable framework.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DutyFlow (Degradation)                      │
│                                                                       │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────────────┐  │
│  │ Phase 1      │    │ Phase 2      │    │ Phase 3               │  │
│  │ poc_loader   │───▶│ rules.json   │───▶│ poc_solver            │  │
│  │              │    │              │    │                       │  │
│  │ Dirty Excel  │    │ Slot defs:   │    │ CP-SAT model:         │  │
│  │ /CSV input   │    │ - Floor 1    │    │ - Coverage constraint │  │
│  │     │        │    │ - Floor 2-3  │    │ - No-clone constraint │  │
│  │     ▼        │    │ - Floor 4-5  │    │ - Leave enforcement   │  │
│  │ TeacherRecord│    │              │    │ - Load balancing      │  │
│  │ dataclass    │    │ Constraints: │    │                       │  │
│  │ List[...]    │    │ - Leave days │    │ Output: bool matrix   │  │
│  │              │    │ - Day-off    │    │ teacher × day × slot  │  │
│  └──────────────┘    │   prefs      │    └───────────────────────┘  │
│                       └──────────────┘               │               │
│                                                       ▼               │
│                                            ┌──────────────────────┐  │
│                                            │ main.py              │  │
│                                            │ Orchestrator + print │  │
│                                            │ (Streamlit optional) │  │
│                                            └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Status Table

| Module | File | Status | Description |
|---|---|---|---|
| Data Loader | `poc_loader.py` | NOT CREATED | Pandas-based dirty-data parser; outputs `List[TeacherRecord]` |
| Rule Config | `rules.json` | NOT CREATED | Static slot/constraint JSON; school-specific hardcoded values |
| CP-SAT Solver | `poc_solver.py` | NOT CREATED | OR-Tools CP-SAT engine; pure constraint algebra, no I/O |
| Orchestrator | `main.py` | STUB (uv-generated) | Linear call chain Phase 1→2→3; needs implementation |
| UI Layer | `streamlit_app.py` | NOT CREATED | Optional Streamlit result viewer; blocked on solver working first |
| Tests | `tests/` | NOT CREATED | Unit tests for loader clean functions and solver constraints |

---

## Data Structures

### TeacherRecord (frozen dataclass)
```python
@dataclass(frozen=True)
class TeacherRecord:
    teacher_id: str           # Unique identifier (from Excel row key)
    name: str                 # Display name
    unavailable: frozenset    # frozenset[tuple[int, int]] — (week_idx, day_idx), 0-indexed
    max_duties_per_week: int  # Loaded from PARAMS_REGISTRY, may be teacher-specific
    notes: str                # Raw original notes string, kept for audit trail
```

### Solver Output
```python
# Boolean assignment matrix
# assignments[teacher_id][week][day][slot] = True/False
assignments: dict[str, list[list[list[bool]]]]
```

---

## Slot Definitions (School-Specific, Hardcoded in rules.json)

Each school day requires coverage on 3 floor zones:

| Slot ID | Zone | Required headcount |
|---|---|---|
| `floor_1` | 1st Floor | 1 person |
| `floor_2_3` | 2nd–3rd Floor | 1 person |
| `floor_4_5` | 4th–5th Floor | 1 person |

> These values must match `rules.json → slots`. Any discrepancy between this table and rules.json
> means rules.json is the authoritative source.

---

## CP-SAT Constraint Hierarchy

1. **Hard — Coverage**: Every slot every active day must have exactly the required headcount.
2. **Hard — No-clone**: A teacher can be assigned to at most 1 slot per day.
3. **Hard — Leave enforcement**: `unavailable` days are absolutely blocked (BoolVar forced to 0).
4. **Soft → Hard — Load balancing**: Total duty count per teacher over the schedule period
   must stay within `[min_duties_total, max_duties_total]` from PARAMS_REGISTRY.

---

## What This PoC Does NOT Handle

- Multi-school generalization
- Dynamic rule parsing from natural language
- Real-time preference updates
- Any form of LLM-based constraint interpretation at runtime
- Historical fairness (cross-period tracking)
