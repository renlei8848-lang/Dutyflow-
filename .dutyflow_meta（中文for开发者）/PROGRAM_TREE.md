# 程序文件树 — DutyFlow（降级版）

> 真实文件树，于 2026-04-06 通过 Glob 工具捕获（不含 .venv 内部和 .git 内部）。
> 任何结构性变更（增删改文件）后，必须重新运行 Glob 并更新本文件。

---

## 文件树

```
DutyFlow(small)/                                    ← 项目根目录
│
├── CLAUDE.md                                       ← Claude 会话指南与黄金规则（本项目的最高法）
├── CLAUDE(中文for开发者).md                         ← CLAUDE.md 的中文镜像（供开发者阅读）
├── Requirment.md                                   ← 排班约束说明文档（硬约束/软约束/数据字段）
├── pyproject.toml                                  ← uv 项目清单；name="dutyflow"，requires-python=">=3.12"
├── uv.lock                                         ← 依赖锁定文件（由 `uv lock` 生成）
├── .python-version                                 ← 固定 Python 3.12 供 uv 自动选择
├── .env                                            ← D 盘缓存路径环境变量（UV_CACHE_DIR、HF_HOME 等）
├── README.md                                       ← 存根 README（uv init 自动生成，尚未填写）
├── main.py                                         ← 存根编排器（uv init 自动生成，待实现）
│
├── clean_schedule.py                               ← 独立数据清洗脚本（非运行时模块）
│                                                      读写 c:/Users/31249/Desktop/晚自修排版.xlsx：
│                                                      · 标准化"次数"sheet 的楼层字段（2/3楼→2-3楼，4/5楼→4-5楼）
│                                                      · 补录5位缺失老师（仅填充空字段，不覆盖已有数据）
│                                                      · 生成/刷新"清洗后数据"sheet（含历史值班统计）
│                                                      每次新增月份sheet后重跑此脚本即可。
│
├── .dutyflow_meta/                                 ← AI 可读项目状态（英文，Claude 读此目录）
│   ├── ARCHITECTURE.md                             ← 系统设计、模块状态表、数据结构（英文）
│   ├── PARAMS_REGISTRY.yaml                        ← 所有数字常量与配置值（英文，唯一来源）
│   ├── TECHNICAL_DEBT_&_TODO.md                   ← 活跃与已完成的技术债/待办（英文）
│   └── PROGRAM_TREE.md                             ← 磁盘真实结构注释（英文）
│
├── .dutyflow_meta（中文for开发者）/                ← 人类可读项目状态（中文，开发者读此目录）
│   ├── ARCHITECTURE.md                             ← 系统架构、模块状态表（中文镜像）
│   ├── PARAMS_REGISTRY.yaml                        ← 参数注册表（中文注释镜像）
│   ├── TECHNICAL_DEBT_&_TODO.md                   ← 技术债与待办（中文镜像）
│   └── PROGRAM_TREE.md                             ← 本文件
│
├── .venv/                                          ← 本地 Python 虚拟环境（CPython 3.12.13，来自 D 盘）
│   └── Scripts/python.exe                          ← 解释器路径指向 D:\...\GlobalCache\uv_python\...
│
└── .git/                                           ← Git 仓库（main 分支，已有初始提交）
```

---

## 外部数据文件（不在仓库中）

```
c:/Users/31249/Desktop/
└── 晚自修排版.xlsx                                 ← 排班数据源文件（含个人信息，不纳入 git）
    ├── sheet: 次数                                 ← 教师名单（由 clean_schedule.py 清洗）
    ├── sheet: 清洗后数据                            ← 生成输出：名单 + 历史值班统计
    └── sheets: 9月 … 4月                           ← 月度排班表（clean_schedule.py 自动检测）
```

---

## 待创建文件（规划中）

```
DutyFlow(small)/
├── poc_loader.py                   ← 阶段1：脏 Excel/CSV → List[TeacherRecord]
├── poc_solver.py                   ← 阶段3：CP-SAT 引擎 → 赋值矩阵
├── rules.json                      ← 阶段2：静态槽位与约束配置
├── streamlit_app.py                ← 可选：Streamlit 结果查看器（求解器先通过后再做）
│
└── tests/                          ← 单元测试
    ├── test_loader.py              ← 测试 poc_loader 清洗函数
    └── test_solver.py              ← 测试求解器约束满足性
```

---

## 更新方法

新增或删除文件后，更新上方文件树。
