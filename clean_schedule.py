"""
clean_schedule.py — 晚自修排版.xlsx 数据清洗脚本

功能：
1. "次数"sheet 楼层标准化（2/3楼→2-3楼，4/5楼→4-5楼）
2. "次数"sheet 为班主任追加"班主任"标签（Col E 要求）
3. "次数"sheet 末尾补录5位排班表中存在但名单中缺失的老师
4. 新建"清洗后数据"sheet，汇总各老师历史值班统计
"""

import sys
import openpyxl
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

# ── 配置 ────────────────────────────────────────────────────────────────────
EXCEL_PATH = r"c:/Users/31249/Desktop/晚自修排版.xlsx"

BANZHUREN = {
    "胡晓娴", "丁亚男", "蒋寅", "许仲", "叶云", "吴徐帆",
    "陆子辰", "陆梦霞", "王仕全", "金丹萍", "毛建伟", "蓝申剑",
    "熊颖", "钟靖", "杨朋昊",
    "肖中海",
}

# 在月份排班表中出现但"次数"名单中缺失的老师（含已知元数据）
MISSING_TEACHERS = [
    {"name": "余海雷", "subject": None,  "grade": None, "req": "不排了", "floor": None},
    {"name": "刘杨",   "subject": "数学", "grade": None, "req": None,    "floor": None},
    {"name": "潘有容", "subject": "化学", "grade": None, "req": None,    "floor": None},
    {"name": "王詹航", "subject": None,  "grade": None, "req": "不排了", "floor": None},
    {"name": "田宇成", "subject": "物理", "grade": None, "req": None,    "floor": None},
]

# 月份sheet由运行时动态检测（排除固定sheet），无需手动维护
EXCLUDE_SHEETS = {"次数", "清洗后数据", "test"}

FLOOR_MAP = {
    "2楼": "2-3楼",
    "3楼": "2-3楼",
    "4楼": "4-5楼",
    "5楼": "4-5楼",
}

VALID_DAYS = {"一", "二", "三", "四", "五", "六", "日"}


def extract_day(raw) -> str | None:
    """统一处理'星期三'和'三'两种格式，返回单字或 None。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if s.startswith("星期") and len(s) == 3:
        return s[-1]
    return s if s in VALID_DAYS else None

# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def normalize_floor(floor: str | None) -> str | None:
    if floor is None:
        return None
    return FLOOR_MAP.get(str(floor).strip(), str(floor).strip())


def find_header_row_idx(ws) -> int | None:
    """返回包含"星期"的行号（1-based）。"""
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == "星期":
                return cell.row
    return None


def col_index_by_name(ws, header_row_idx: int, name: str) -> int | None:
    """在 header_row_idx 行中找到值为 name 的列号（1-based）。"""
    for cell in ws[header_row_idx]:
        if cell.value == name:
            return cell.column
    return None


# ── Step 1：修改"次数"sheet ──────────────────────────────────────────────────

def patch_cishu_sheet(ws_cishu: openpyxl.worksheet.worksheet.Worksheet):
    existing_teachers: set[str] = set()
    last_id = 0

    for row in ws_cishu.iter_rows(min_row=2):
        id_cell     = row[0]   # Col A：序号
        name_cell   = row[1]   # Col B：姓名
        yaoqiu_cell = row[4]   # Col E：要求
        floor_cell  = row[5]   # Col F：楼层

        name = name_cell.value
        if not name:
            continue

        name = str(name).strip()
        existing_teachers.add(name)

        # 记录最大序号
        if id_cell.value and isinstance(id_cell.value, (int, float)):
            last_id = max(last_id, int(id_cell.value))

        # 楼层标准化
        floor_cell.value = normalize_floor(floor_cell.value)

        # 清除要求列中可能已写入的"班主任"标签
        if yaoqiu_cell.value and "班主任" in str(yaoqiu_cell.value):
            cleaned = "，".join(
                p for p in str(yaoqiu_cell.value).split("，") if p.strip() != "班主任"
            )
            yaoqiu_cell.value = cleaned if cleaned else None

    # 补录或更新缺失老师
    name_to_row: dict[str, tuple] = {}
    for row in ws_cishu.iter_rows(min_row=2):
        if row[1].value:
            name_to_row[str(row[1].value).strip()] = row

    added = 0
    for teacher in MISSING_TEACHERS:
        tname = teacher["name"]
        if tname in name_to_row:
            # 已存在：仅用元数据填充仍为空的字段，不覆盖用户已填写的值
            row = name_to_row[tname]
            if row[2].value is None and teacher["subject"]:
                row[2].value = teacher["subject"]
            if row[3].value is None and teacher["grade"]:
                row[3].value = teacher["grade"]
            if row[4].value is None and teacher["req"]:
                row[4].value = teacher["req"]
            if row[5].value is None and teacher["floor"]:
                row[5].value = normalize_floor(teacher["floor"])
        else:
            # 不存在：追加新行
            last_id += 1
            ws_cishu.append([
                last_id, tname,
                teacher["subject"], teacher["grade"],
                teacher["req"],
                normalize_floor(teacher["floor"]) if teacher["floor"] else None,
            ])
            added += 1
            print(f"  补录：{tname}（序号 {last_id}）")

    print(f"次数 sheet 修改完成，补录 {added} 人。")


# ── Step 2：统计月份排班 ──────────────────────────────────────────────────────

def collect_duty_counts(wb) -> tuple[dict, dict, dict, int, list[str]]:
    total_count   = defaultdict(int)
    friday_count  = defaultdict(int)
    sunday_count  = defaultdict(int)
    active_months = 0
    active_list   = []

    monthly_sheets = [s for s in wb.sheetnames if s not in EXCLUDE_SHEETS]

    for sheet_name in monthly_sheets:
        if not sheet_name:
            continue

        ws = wb[sheet_name]
        hdr_row = find_header_row_idx(ws)
        if hdr_row is None:
            print(f"  跳过（未找到'星期'列）：{sheet_name}")
            continue

        col_day  = col_index_by_name(ws, hdr_row, "星期")
        col_1    = col_index_by_name(ws, hdr_row, "1楼")
        col_23   = col_index_by_name(ws, hdr_row, "2-3楼")
        col_45   = col_index_by_name(ws, hdr_row, "4-5楼")

        floor_cols = [c for c in [col_1, col_23, col_45] if c is not None]

        has_data = False
        for row in ws.iter_rows(min_row=hdr_row + 1):
            raw_day = row[col_day - 1].value if col_day else None
            day = extract_day(raw_day)
            if day is None:
                continue

            is_fri = (day == "五")
            is_sun = (day == "日")
            has_data = True

            names: list[str] = []
            for col_idx in floor_cols:
                val = row[col_idx - 1].value
                if val:
                    names.append(str(val).strip())

            for name in names:
                if name == "全体班主任":
                    for bzr in BANZHUREN:
                        total_count[bzr] += 1
                        if is_fri:
                            friday_count[bzr] += 1
                        if is_sun:
                            sunday_count[bzr] += 1
                else:
                    total_count[name] += 1
                    if is_fri:
                        friday_count[name] += 1
                    if is_sun:
                        sunday_count[name] += 1

        if has_data:
            active_months += 1
            active_list.append(sheet_name)

    print(f"有数据的月份（{active_months}个）：{active_list}")
    return total_count, friday_count, sunday_count, active_months, active_list


# ── Step 3：生成"清洗后数据"sheet ─────────────────────────────────────────────

def build_clean_sheet(
    wb,
    ws_cishu,
    total_count: dict,
    friday_count: dict,
    sunday_count: dict,
    active_months: int,
):
    # 先把现有"清洗后数据"的 A-F 列读出来缓存（保留人工编辑内容）
    # 键：姓名；值：(xueke, nianji, yaoqiu, floor) — 序号重新按顺序编
    preserved_af: dict[str, tuple] = {}
    if "清洗后数据" in wb.sheetnames:
        for row in wb["清洗后数据"].iter_rows(min_row=2, values_only=True):
            if row[1]:  # 姓名不为空
                name = str(row[1]).strip()
                preserved_af[name] = (row[2], row[3], row[4], row[5], row[6])  # 学科,年级,要求,楼层,是否班主任
        del wb["清洗后数据"]
        print(f"  已读取 {len(preserved_af)} 条 A-G 列缓存（人工编辑内容将被保留）。")

    # 插入在"次数"之后
    cishu_idx = wb.sheetnames.index(wb.sheetnames[0])
    ws_clean = wb.create_sheet("清洗后数据", cishu_idx + 1)

    denom_label = f"/{active_months}月" if active_months else ""
    headers = [
        "序号", "姓名", "教学学科", "教学年级", "要求", "楼层", "是否班主任",
        "历史总次数", "历史周五次数", "历史周日次数",
        f"月均次数{denom_label}", f"月均周五{denom_label}", f"月均周日{denom_label}",
    ]
    ws_clean.append(headers)

    seq = 1
    for row in ws_cishu.iter_rows(min_row=2, values_only=True):
        name = row[1]
        if not name:
            continue
        name = str(name).strip()

        if name in preserved_af:
            # 优先使用"清洗后数据"中保留的 A-G 值（人工编辑内容）
            xueke, nianji, yaoqiu, floor, is_bzr = preserved_af[name]
        else:
            # 新增老师：从"次数"sheet 读取，是否班主任由 BANZHUREN 集合决定
            xueke  = row[2]
            nianji = row[3]
            yaoqiu = row[4]
            floor  = row[5]
            is_bzr = "是" if name in BANZHUREN else "否"

        total   = total_count.get(name, 0)
        friday  = friday_count.get(name, 0)
        sunday  = sunday_count.get(name, 0)

        if active_months > 0:
            avg_total = round(total  / active_months, 2)
            avg_fri   = round(friday / active_months, 2)
            avg_sun   = round(sunday / active_months, 2)
        else:
            avg_total = avg_fri = avg_sun = 0

        ws_clean.append([
            seq, name, xueke, nianji, yaoqiu, floor, is_bzr,
            total, friday, sunday, avg_total, avg_fri, avg_sun,
        ])
        seq += 1

    print(f"清洗后数据 sheet 写入完成，共 {seq - 1} 行。")


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    print(f"加载文件：{EXCEL_PATH}")
    wb = openpyxl.load_workbook(EXCEL_PATH)

    cishu_name = wb.sheetnames[0]
    print(f"次数 sheet 名：{cishu_name}")
    ws_cishu = wb[cishu_name]

    print("\n── Step 1：修改次数 sheet ──")
    patch_cishu_sheet(ws_cishu)

    print("\n── Step 2：统计月份排班 ──")
    total_count, friday_count, sunday_count, active_months, _ = collect_duty_counts(wb)

    print("\n── Step 3：生成清洗后数据 ──")
    build_clean_sheet(wb, ws_cishu, total_count, friday_count, sunday_count, active_months)

    print(f"\n保存文件：{EXCEL_PATH}")
    wb.save(EXCEL_PATH)
    print("完成！")


if __name__ == "__main__":
    main()
