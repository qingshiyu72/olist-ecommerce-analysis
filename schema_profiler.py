# -*- coding: utf-8 -*-
"""
L2 接入画像：给一张不认识的表做列画像，回答三个问题——
  ① 哪列是数值（能算）② 哪列能当维度（能分组）③ 该求和还是该求平均

这是「接任意数据源」的第一步。没有它，Agent 面对陌生表不知道该 group by 谁、该 sum 谁。

用法:
    python schema_profiler.py                 # 默认画像 order_fact
    python schema_profiler.py olist_orders    # 指定表
    python schema_profiler.py --tables        # 列出所有表
"""
import os
import re
import sqlite3
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "olist.db")

SAMPLE = 3000          # 类型推断取样行数（n_unique 仍用 SQL 精确统计）
TYPE_HIT = 0.8         # 80% 命中即判定为该类型

DATE_RE = re.compile(r"^\d{4}[-/.]\d{1,2}([-/.]\d{1,2})?([ T]\d{1,2}:\d{2})?")
NUM_RE = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$")

# 名称含这些词 → 该列是"率/均价"类，应求平均而非求和
AVG_KW = ("率", "均", "评分", "单价", "价格", "占比", "比例", "rate", "avg", "mean",
          "score", "price", "ratio", "pct", "percent")

# 名称含这些词 → 时长类，求和没有意义，只能求平均
DUR_KW = ("天", "时长", "耗时", "间隔", "days", "duration", "delay", "hours",
          "minutes", "elapsed", "latency", "age")


def to_num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("¥", "").replace("$", "").replace("%", "")
    if not NUM_RE.match(s):
        return None
    return float(s)


def looks_date(v):
    return bool(v is not None and DATE_RE.match(str(v).strip()))


def infer_type(values):
    """按 80% 阈值推断 number / date / text"""
    filled = [v for v in values if v is not None and str(v).strip() != ""]
    if not filled:
        return "empty", 0.0
    num_hit = sum(1 for v in filled if to_num(v) is not None) / len(filled)
    date_hit = sum(1 for v in filled if looks_date(v)) / len(filled)
    if date_hit >= TYPE_HIT and date_hit >= num_hit:
        return "date", date_hit
    if num_hit >= TYPE_HIT:
        return "number", num_hit
    return "text", 1 - max(num_hit, date_hit)


def suggest(col, itype, n_uniq, n_rows, samples):
    """返回 (角色, 聚合建议)"""
    low = col.lower()

    if itype == "date":
        return "时间列", "—"

    if itype == "number":
        vals = [to_num(v) for v in samples if to_num(v) is not None]
        # 0/1 二值列 = 比率/标记，必须求平均，否则求和没有意义
        # 唯一值 1 也要覆盖：全 0 的标记列同样应报"占比 0%"
        if vals and set(vals) <= {0.0, 1.0} and n_uniq <= 2:
            return "比例/标记", "avg（0-1 取均值得百分比）"
        if any(k in low for k in DUR_KW):
            return "指标（时长类）", "avg"
        if any(k in low for k in AVG_KW):
            return "指标（率/均价类）", "avg"
        if n_uniq <= 20 and vals and all(float(v).is_integer() for v in vals):
            return "指标（等级/计数）", "avg 或 sum 需确认语义"
        return "指标", "sum"

    # text
    if n_uniq == n_rows:
        return "主键/ID", "—"
    if 2 <= n_uniq <= 60:
        return "维度", "可 group by"
    return "高基数列", "不建议直接分组（唯一值过多）"


def profile(conn, table):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{table}])")]
    if not cols:
        print(f"表 {table} 不存在或没有列")
        return 1

    n_rows = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    sample_rows = conn.execute(f"SELECT * FROM [{table}] LIMIT {SAMPLE}").fetchall()
    print("=" * 96)
    print(f"表 {table}　{n_rows:,} 行 × {len(cols)} 列　类型推断取样 {len(sample_rows):,} 行")
    print("=" * 96)
    print(f"{'列名':<24}{'推断类型':<10}{'唯一值':>8}{'缺失率':>8}  {'角色':<18}{'聚合建议'}")

    rec = {"指标": [], "维度": [], "时间列": [], "风险": []}
    for i, c in enumerate(cols):
        vals = [r[i] for r in sample_rows]
        itype, conf = infer_type(vals)
        n_uniq = conn.execute(f"SELECT COUNT(DISTINCT [{c}]) FROM [{table}]").fetchone()[0]
        null_pct = 100.0 * sum(1 for v in vals if v is None or str(v).strip() == "") / max(len(vals), 1)
        role, agg = suggest(c, itype, n_uniq, n_rows, vals)

        print(f"{c[:23]:<24}{itype:<10}{n_uniq:>8,}{null_pct:>7.2f}%  {role:<18}{agg}")

        if role.startswith("指标"):
            rec["指标"].append(f"{c}({agg.split('（')[0].split()[0]})")
        elif role == "维度":
            rec["维度"].append(f"{c}({n_uniq})")
        elif role == "时间列":
            rec["时间列"].append(c)

        if null_pct > 5:
            rec["风险"].append(f"{c} 缺失 {null_pct:.2f}%")
        if role == "高基数列":
            rec["风险"].append(f"{c} 唯一值 {n_uniq:,}，不能直接 group by")
        if itype in ("number", "text") and 0 < conf and itype == "number" and conf < 0.95:
            rec["风险"].append(f"{c} 仅 {conf*100:.0f}% 可解析为数值，可能有脏值")

    print("-" * 96)
    print(f"  时间列：{', '.join(rec['时间列']) or '无'}")
    print(f"  可用维度：{', '.join(rec['维度'][:8]) or '无'}")
    print(f"  可用指标：{', '.join(rec['指标'][:10]) or '无'}")
    if rec["风险"]:
        print("  注意事项：")
        for r in rec["风险"][:8]:
            print(f"    - {r}")
    print("=" * 96)
    print("提示：维度列建议控制在 2~60 个唯一值；指标列的 sum/avg 请按业务语义复核")
    return 0


def main():
    if not os.path.exists(DB):
        print(f"未找到 {DB}，请先跑 python import_to_sqlite.py")
        return 1
    conn = sqlite3.connect(DB)
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--tables":
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            print("\n".join(names))
            return 0
        table = sys.argv[1] if len(sys.argv) > 1 else "order_fact"
        # 表名白名单校验，避免拼接到 SQL 时出错
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                              (table,)).fetchone()
        if not exists:
            print(f"表 {table} 不存在。用 --tables 查看可用的表")
            return 1
        return profile(conn, table)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
