# 程序文件树 — DutyFlow（降级版）

> 真实文件树，最后更新 2026-04-07（日历重构；新增 scheduling_state.json、special_dates.json；main.py 完整实现）。
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
│
├── main.py                                         ← 编排器：读状态→推算月份→求解→导出
│                                                      · 读取 scheduling_state.json 推算下一月
│                                                      · 读取 special_dates.json 加载目标月特殊配置
│                                                      · 调用 load_teacher_records → DutySolver → export_to_excel
│                                                      · 不更新 scheduling_state.json（由 clean_schedule.py 归档时更新）
│
├── poc_loader.py                                   ← 阶段1数据加载器：读取"清洗后数据"→ List[TeacherRecord]
│                                                      · 所有配置从 PARAMS_REGISTRY.yaml 读取，不硬编码
│                                                      · 定义 TeacherRecord 冻结数据类
│                                                      · load_teacher_records(excel_path) → list[TeacherRecord]
│                                                      · __main__ 块用于手动验证
│
├── poc_solver.py                                   ← CP-SAT 求解器：List[TeacherRecord] → "X年X月排班（暂定）" sheet
│                                                      · build_schedule_days(year, month, special_cfg) → list[ScheduleDay]
│                                                        真实日历枚举（节假日排除、调休周六加入、全体班主任日抑制）
│                                                      · DutySolver(records, config, target_month, special_dates)
│                                                        target_month: "YYYY-MM"；num_weeks 从日历推导（非硬编码）
│                                                      · 变量键 (tid, week_idx, day_of_week, slot_id) 不变
│                                                      · 6个硬约束（HC-1覆盖、HC-2无分身、HC-3周上限、
│                                                        HC-4月上限、HC-5周末互斥、HC-6极差≤1）
│                                                      · 软目标（SC-1~SC-5）：学科/日期偏好 + 间隔奖励 +
│                                                        非BZ双次偏好 + 月均偏差惩罚 + BZ非周末惩罚 + 非BZ周末双排惩罚
│                                                      · export_to_excel() 输出真实日期标签（如"5月6日(周三)"）
│                                                      · __main__ 块：读 scheduling_state.json 推算月份后独立运行
│
├── clean_schedule.py                               ← 独立数据清洗脚本（非运行时模块）
│                                                      读写 c:/Users/31249/Desktop/晚自修排版.xlsx：
│                                                      · 标准化"次数"sheet 楼层字段（无补录缺失老师逻辑）
│                                                      · 只扫描格式严格为"YYYY年M月"的 sheet 统计历史次数
│                                                      · collect_duty_counts() 兼容旧"星期"列和新"日期"列格式
│                                                      · sync_state_file() 同步 scheduling_state.json
│                                                      · 重跑时保留"清洗后数据"A-G列（人工编辑不丢失）
│                                                      · BANZHUREN：16人
│
├── scheduling_state.json                           ← 月份状态文件（运行时可变）
│                                                      · last_generated: 上次生成的月份 "YYYY-MM"
│                                                      · generated_months: 已生成月份列表（审计日志）
│
├── special_dates.json                              ← 每月特殊日期配置（运行前手动编辑）
│                                                      · 以 "YYYY-MM" 为键；字段：holiday_ranges / extra_workdays /
│                                                        all_bz_required_days / notes
│
├── 临时要求.md                                      ← 历史记录，已被 special_dates.json 取代（可删除）
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
└── .git/                                           ← Git 仓库（main 分支）
```

---

## 外部数据文件（不在仓库中）

```
c:/Users/31249/Desktop/
└── 晚自修排版.xlsx                                 ← 排班数据源文件（含个人信息，不纳入 git）
    ├── sheet: 次数                                 ← 教师名单（由 clean_schedule.py 清洗）
    ├── sheet: 清洗后数据                            ← 生成输出：名单 + 历史值班统计
    ├── sheets: 2025年9月 … 2026年4月               ← 月度排班表（格式：YYYY年M月，正则匹配自动检测）
    └── sheet: YYYY年M月排班（暂定）                 ← 求解器输出（含"排班"后缀，不计入历史统计；用户确认后改名归档）
```

---

## 待创建文件（规划中）

```
DutyFlow(small)/
├── streamlit_app.py                ← 可选：Streamlit 结果查看器（求解器先通过后再做）
│
└── tests/                          ← 单元测试
    ├── test_loader.py              ← 测试 poc_loader 清洗函数
    └── test_solver.py              ← 测试求解器约束满足性
```

---

## 更新方法

新增或删除文件后，更新上方文件树。
