# CLAUDE.md — DutyFlow (Degradation PoC)

> This file is the **single source of truth** for every Claude session in this project.
> Read this file completely before writing any code or making any suggestions.

---

## 1. Project Overview

**DutyFlow (Degradation)** is a white-box, hardcoded, linear-flow Proof of Concept for school duty-roster scheduling.
It is the degraded/standalone version of the DutyFlow SaaS platform — designed to validate that OR-Tools CP-SAT
can correctly solve a specific school's scheduling constraints before building a generalized abstraction layer.

**Design philosophy: no black boxes.**
- No LLM at runtime. Claude is used *offline only* for data cleaning assistance and code generation.
- No dynamic rule parsing. All constraints are hardcoded or read from `rules.json`.
- No framework magic. Data flows linearly: raw Excel → cleaned structs → CP-SAT → output table.
- Reproducibility is non-negotiable. Given the same inputs, the solver must produce the exact same output every run.

---

## 2. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Runtime language | Python 3.12.13 (uv-managed) | See interpreter path in §6 |
| Solver engine | Google OR-Tools CP-SAT | Core dependency, version pinned in pyproject.toml |
| Data ingestion | Pandas + openpyxl | Dirty Excel/CSV → `TeacherRecord` dataclass |
| UI (optional) | Streamlit | Result visualization only; terminal solve must pass first |
| Offline assistant | Claude 3.7 Sonnet API | Data cleaning & code gen ONLY — **never imported at runtime** |
| Env management | uv | No conda/mamba/pip-direct. Always `uv pip install --python .venv/Scripts/python.exe` |

---

## 3. Mandatory Initialization Protocol

**At the start of EVERY session, before writing any code:**

1. Read `.dutyflow_meta/ARCHITECTURE.md` — confirm current module status
2. Read `.dutyflow_meta/PARAMS_REGISTRY.yaml` — load all canonical constants
3. Read `.dutyflow_meta/TECHNICAL_DEBT_&_TODO.md` — check active items
4. Read `.dutyflow_meta/PROGRAM_TREE.md` — verify real file structure

If any of these files conflict with code on disk, **trust the code on disk** and update the meta file.
Never trust memory of previous sessions — always re-read.

---

## 4. Golden Rules (Non-Negotiable)

### 4.1 No Hallucinated Parameters
- Every numeric constant, threshold, or configuration value **must exist in `PARAMS_REGISTRY.yaml`**.
- Never invent a value inline (e.g., `max_shifts = 5`). Reference the registry: load from YAML at module init.
- If a needed parameter is missing from the registry, add it there first, then reference it.

### 4.2 No Runtime LLM Calls
- The Claude API must never appear in `poc_loader.py`, `poc_solver.py`, or any runtime module.
- Acceptable usage: standalone preprocessing scripts, Jupyter notebooks, one-off data cleaning tools.
- If you see an `import anthropic` in a runtime file, that is a bug — flag it immediately.

### 4.3 No Global Environment Pollution
- Never run `uv pip install --system`.
- Never `pip install` directly. Always route through: `uv pip install --python .venv/Scripts/python.exe`.
- Never activate .venv via shell sourcing in automated scripts — use the full Python path instead.

### 4.4 Solver Determinism
- CP-SAT must be seeded and configured to produce identical output on identical input.
- Never use `random` or `time.time()` as part of constraint logic.
- All solver parameters (time limit, num workers, etc.) must come from `PARAMS_REGISTRY.yaml`.

### 4.5 Documentation Sync
- After any structural change (new file, renamed module, changed constant), update **all** of the following in the same response:
  - `.dutyflow_meta/PROGRAM_TREE.md` + `.dutyflow_meta（中文for开发者）/PROGRAM_TREE.md`
  - `.dutyflow_meta/PARAMS_REGISTRY.yaml` + `.dutyflow_meta（中文for开发者）/PARAMS_REGISTRY.yaml` (if constants changed)
  - `.dutyflow_meta/ARCHITECTURE.md` + `.dutyflow_meta（中文for开发者）/ARCHITECTURE.md` (if module status changed)
  - `CLAUDE(中文for开发者).md` (if any section in this file changed)
- Claude reads only the English `.dutyflow_meta/` and `CLAUDE.md`.
  The Chinese mirrors (`.dutyflow_meta（中文for开发者）/` and `CLAUDE(中文for开发者).md`) are for the human developer — but they must be kept in sync.

---

## 5. Core Coding Conventions

### Module Boundaries
```
poc_loader.py      ← Phase 1: dirty data in, List[TeacherRecord] out. No solver logic.
rules.json         ← Phase 2: static slot/constraint config. No Python logic.
poc_solver.py      ← Phase 3: CP-SAT engine. Accepts TeacherRecord list + rules dict. No I/O.
main.py            ← Orchestrator only. Calls Phase 1→2→3 in sequence. No business logic.
```

### Data Structures
- `TeacherRecord` is a frozen dataclass. Fields must not be mutated after construction.
- All "unavailability" info (leave, day-off preferences) is resolved to `Set[Tuple[int,int]]`
  (week_index, day_index) by `poc_loader.py` before reaching the solver.

### Error Handling
- `poc_loader.py`: raise `ValueError` with row number on any unresolvable dirty cell.
- `poc_solver.py`: if CP-SAT returns INFEASIBLE, raise `RuntimeError` with the constraint that
  was most recently added (to aid debugging). Never silently return an empty schedule.

### File Naming
- All source files: `snake_case.py`
- Config files: `snake_case.json` / `snake_case.yaml`
- Test files: `test_<module_name>.py` in `/tests/`

---

## 6. Environment Constraints

### Python Interpreter (D-Drive Only)
```
D:\SoftwareCode\MyCyberLab\GlobalCache\uv_python\cpython-3.12.13-windows-x86_64-none\python.exe
```
- `.venv/pyvenv.cfg` home line must start with `D:\`
- Verify after any venv recreation: `cat .venv/pyvenv.cfg`

### C-Drive Read-Only Principle
No cache, model weights, or tool data may be written to C drive.
All redirects are set in `.env` (loaded by python-dotenv or shell before any install):

| Variable | D-Drive Path |
|---|---|
| `UV_CACHE_DIR` | `D:\SoftwareCode\MyCyberLab\GlobalCache\uv` |
| `UV_TOOL_DIR` | `D:\SoftwareCode\MyCyberLab\GlobalCache\uv_tools` |
| `UV_PYTHON_INSTALL_DIR` | `D:\SoftwareCode\MyCyberLab\GlobalCache\uv_python` |
| `PIP_CACHE_DIR` | `D:\SoftwareCode\MyCyberLab\GlobalCache\pip` |
| `HF_HOME` | `D:\SoftwareCode\MyCyberLab\GlobalCache\huggingface` |
| `TORCH_HOME` | `D:\SoftwareCode\MyCyberLab\GlobalCache\torch` |
| `NUMBA_CACHE_DIR` | `D:\SoftwareCode\MyCyberLab\GlobalCache\numba` |
| `MPLCONFIGDIR` | `D:\SoftwareCode\MyCyberLab\GlobalCache\matplotlib` |
| `POLARS_TEMP_DIR` | `D:\SoftwareCode\MyCyberLab\GlobalCache\polars_temp` |

> Note: `supabase.exe` is present in GlobalCache (Supabase CLI binary) — not a Python dependency.

### Installing New Libraries — Mandatory Pre-Check
Before installing any new library:
1. Check if it has known C-drive default cache dirs (e.g., `~/.cache/`, `%APPDATA%/`).
2. If yes, set the appropriate redirect env var **before** running `uv pip install`.
3. If unsure, run the install then check for new dirs under `C:\Users\` immediately after.
4. Run uv commands via `bash --norc --noprofile -c '...'` to bypass the `_venv_auto_activate`
   shell hook that causes exit 127 in this environment.

---

## 7. Three-Phase Data Flow (Immutable)

```
[Raw Excel/CSV]
      │
      ▼  poc_loader.py
[List[TeacherRecord]]  ←→  [rules.json]
      │
      ▼  poc_solver.py (CP-SAT)
[Schedule Matrix: teacher × day × slot]
      │
      ▼  main.py / Streamlit
[Output: console table / HTML render]
```

This flow is linear and single-pass. There is no feedback loop between phases at runtime.

---

## 8. Plan Mode Rules

When operating in **Plan Mode** (i.e., designing an approach before writing code):

### 8.1 Output Must Be Minimal
- State only: what will be changed, which files are affected, and why.
- Use bullet points or a short numbered list. No paragraphs.
- No code blocks, no diffs, no inline snippets in plan output.

### 8.2 No Code in Plan Output
- Never output actual code, function bodies, or line-by-line changes during planning.
- If a specific API signature is critical to the plan, mention the function name only — not its implementation.

### 8.3 Plan Format (required)
```
Files affected: <comma-separated list>
Changes:
  - <file>: <one-line description of change>
  - ...
Rationale: <one sentence max>
Risks / blockers: <one sentence, or "none">
```

### 8.4 Confirm Before Executing
- After presenting the plan, wait for explicit user approval before writing any code.
- If the user says "go" / "ok" / "proceed", begin implementation immediately without re-summarizing the plan.
