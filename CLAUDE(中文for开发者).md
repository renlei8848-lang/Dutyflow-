# CLAUDE（中文for开发者）.md — DutyFlow（降级版 PoC）

> 本文件是 `CLAUDE.md` 的中文镜像，**仅供人类开发者阅读**。
> Claude 只读 `CLAUDE.md`（英文版）。
> 每次修改 `CLAUDE.md` 时，必须同步更新本文件，保持内容完全一致。

---

## 1. 项目概述

**DutyFlow（降级版）** 是一个白盒化、硬编码、线性单向流的学校值班排班概念验证项目。
它是 DutyFlow SaaS 平台的降级独立版本——目的是在构建通用抽象层之前，先验证 OR-Tools CP-SAT
能否正确解决某所学校的排班约束问题。

**设计理念：不用黑盒。**
- 运行时不调用大模型。Claude 仅在离线数据清洗和代码生成时使用。
- 不做动态规则解析。所有约束硬编码或写入 `rules.json`。
- 不用框架魔法。数据线性流动：原始 Excel → 清洗结构体 → CP-SAT → 输出表格。
- 可复现性不可妥协。相同输入必须每次产生完全相同的结果。

---

## 2. 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 运行时语言 | Python 3.12.13（uv 管理） | 解释器路径见第 6 节 |
| 求解引擎 | Google OR-Tools CP-SAT | 核心依赖，版本锁定于 pyproject.toml |
| 数据摄入 | Pandas + openpyxl | 脏 Excel/CSV → `TeacherRecord` 数据类 |
| UI（可选） | Streamlit | 仅用于结果可视化；终端求解必须先通过 |
| 离线辅助 | Claude 3.7 Sonnet API | 仅用于数据清洗和代码生成 — **运行时绝不导入** |
| 环境管理 | uv | 禁用 conda/mamba/直接 pip。始终用 `uv pip install --python .venv/Scripts/python.exe` |

---

## 3. 强制初始化协议

**每次会话开始，写任何代码之前：**

1. 读 `.dutyflow_meta/ARCHITECTURE.md` — 确认当前模块状态
2. 读 `.dutyflow_meta/PARAMS_REGISTRY.yaml` — 加载所有规范常量
3. 读 `.dutyflow_meta/TECHNICAL_DEBT_&_TODO.md` — 检查活跃待办
4. 读 `.dutyflow_meta/PROGRAM_TREE.md` — 确认真实文件结构

如果上述文件与磁盘上的代码冲突，**以磁盘代码为准**，并更新元数据文件。
永远不要依赖上一次会话的记忆——必须重新读取。

---

## 4. 黄金规则（不可违背）

### 4.1 禁止幻觉参数
- 所有源文件中使用的数字常量、阈值或配置值，**必须先存在于 `PARAMS_REGISTRY.yaml` 中**。
- 不得在代码中直接写死数字（如 `max_shifts = 5`）。从注册表中引用：在模块初始化时加载 YAML。
- 如果需要的参数在注册表中不存在，先在那里添加，再引用。

### 4.2 运行时禁止调用大模型
- Claude API 不得出现在 `poc_loader.py`、`poc_solver.py` 或任何运行时模块中。
- 可接受的用法：独立预处理脚本、Jupyter 笔记本、一次性数据清洗工具。
- 如果在运行时文件中看到 `import anthropic`，那是 bug——立即标记。

### 4.3 禁止污染全局环境
- 不得运行 `uv pip install --system`。
- 不得直接 `pip install`。始终通过：`uv pip install --python .venv/Scripts/python.exe`。
- 不得在自动化脚本中通过 shell 激活 .venv——改用完整 Python 路径。

### 4.4 求解器确定性
- CP-SAT 必须配置为对相同输入产生完全相同的输出。
- 不得在约束逻辑中使用 `random` 或 `time.time()`。
- 所有求解器参数（时间限制、工作线程数等）必须来自 `PARAMS_REGISTRY.yaml`。

### 4.5 文档同步协议
修改任何结构（新增文件、重命名模块、修改常量）后，必须在同一次响应中更新以下**全部**文件：
- `.dutyflow_meta/PROGRAM_TREE.md` + `.dutyflow_meta（中文for开发者）/PROGRAM_TREE.md`
- `.dutyflow_meta/PARAMS_REGISTRY.yaml` + `.dutyflow_meta（中文for开发者）/PARAMS_REGISTRY.yaml`（如常量有变）
- `.dutyflow_meta/ARCHITECTURE.md` + `.dutyflow_meta（中文for开发者）/ARCHITECTURE.md`（如模块状态有变）
- `CLAUDE(中文for开发者).md`（如本文件对应的英文版有变）

Claude 只读英文版 `.dutyflow_meta/` 和 `CLAUDE.md`。
中文镜像（`.dutyflow_meta（中文for开发者）/` 和 `CLAUDE(中文for开发者).md`）供人类开发者阅读——但必须保持同步。

---

## 5. 核心编码规范

### 模块边界
```
poc_loader.py      ← 阶段1：脏数据进，List[TeacherRecord] 出。无求解器逻辑。
rules.json         ← 阶段2：静态槽位/约束配置。无 Python 逻辑。
poc_solver.py      ← 阶段3：CP-SAT 引擎。接收数据和规则。无 I/O。
main.py            ← 仅编排器。按顺序调用阶段1→2→3。无业务逻辑。
```

### 数据结构
- `TeacherRecord` 是冻结数据类。构造后字段不得修改。
- 所有"不可用"信息（请假、不排偏好）由 `poc_loader.py` 解析为确定的
  `Set[Tuple[int,int]]`（周索引, 天索引），在到达求解器之前完成。

### 错误处理
- `poc_loader.py`：遇到无法解析的脏单元格时，抛出带行号的 `ValueError`。
- `poc_solver.py`：CP-SAT 返回 INFEASIBLE 时，抛出 `RuntimeError` 并注明最后添加的约束（辅助调试）。永远不要静默返回空排班表。

### 文件命名
- 所有源文件：`snake_case.py`
- 配置文件：`snake_case.json` / `snake_case.yaml`
- 测试文件：`test_<模块名>.py`，放在 `/tests/` 目录

---

## 6. 环境约束

### Python 解释器（仅 D 盘）
```
D:\SoftwareCode\MyCyberLab\GlobalCache\uv_python\cpython-3.12.13-windows-x86_64-none\python.exe
```
- `.venv/pyvenv.cfg` 的 home 行必须以 `D:\` 开头
- 重建 venv 后验证：`cat .venv/pyvenv.cfg`

### C 盘只读原则
任何缓存、模型权重或工具数据不得写入 C 盘。
所有重定向已在 `.env` 中设置（安装前通过 python-dotenv 或 shell 加载）：

| 变量 | D 盘路径 |
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

> 注：GlobalCache 中存在 `supabase.exe`（Supabase CLI 二进制），不是 Python 依赖。

### 安装新库前的强制检查
安装任何新库之前：
1. 检查该库是否有已知的 C 盘默认缓存目录（如 `~/.cache/`、`%APPDATA%/`）。
2. 若有，在运行 `uv pip install` **之前**先设置对应的重定向环境变量。
3. 若不确定，安装后立即检查 `C:\Users\` 下是否出现新目录。
4. 使用 `bash --norc --noprofile -c '...'` 运行 uv 命令，绕过 `_venv_auto_activate`
   shell hook（该 hook 会导致此环境中出现 exit 127 错误）。

---

## 7. 三阶段数据流（不可变）

```
[原始 Excel/CSV]
      │
      ▼  poc_loader.py
[List[TeacherRecord]]  ←→  [rules.json]
      │
      ▼  poc_solver.py（CP-SAT）
[排班矩阵：教师 × 天 × 槽位]
      │
      ▼  main.py / Streamlit
[输出：终端表格 / HTML 渲染]
```

此流程是线性单向单遍的。运行时各阶段之间没有反馈回路。

---

## 8. Plan 模式规则

在 **Plan 模式**下（即在编写代码前设计方案时）：

### 8.1 输出必须极其简约
- 只说明：要改什么、影响哪些文件、为什么。
- 使用项目符号或简短的编号列表。不写段落。
- 计划输出中不包含代码块、diff、行内代码片段。

### 8.2 计划输出中禁止出现代码
- 规划阶段绝不输出实际代码、函数体或逐行修改内容。
- 如果某个 API 签名对计划至关重要，只提及函数名——不写实现。

### 8.3 计划格式（必须遵守）
```
涉及文件：<逗号分隔列表>
变更内容：
  - <文件>：<一行描述>
  - ...
变更原因：<最多一句话>
风险 / 阻塞项：<一句话，或"无">
```

### 8.4 执行前确认
- 提交计划后，等待用户明确批准，再编写任何代码。
- 用户说"go" / "ok" / "好" / "开始"等，立即进入实现，不要重新总结计划。
