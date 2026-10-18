# -*- coding: utf-8 -*-
"""
L4 自动化日报：对任意日期生成一份 Markdown 日报（含质检门禁结论 + 异动判定 + 归因指引）。

用法:
    python build_daily_report.py                  # 默认取数据内最新日 -30 天（避开采集截尾）
    python build_daily_report.py 2018-08-15       # 指定日期
产出:
    reports/daily_YYYY-MM-DD.md

设计说明:
- 异动判定用「近 7 日 vs 前 7 日」，不用单日环比。
  实测单日 GMV 环比中位 19.6%、P90 52.5%，单日阈值会天天报警；
  7 日均线环比 P90 = 9.3%，故取 8% 作为 WARN 线。
- 差评率不进当日结论：评价相对下单有滞后，日粒度会系统性低估，只在 7 日窗口给。
"""
import os
import subprocess
import sys
from datetime import date, timedelta

import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "olist.db")
OUT_DIR = os.path.join(BASE, "reports")

WARN_PCT = 8.0        # 相对指标告警线（7 日均线环比，由历史 P90 校准）
WARN_PP = 2.0         # 迟到率的绝对变化告警线（百分点）


def q(sql, args=()):
    conn = sqlite3.connect(DB)
    try:
        return conn.execute(sql, args).fetchone()
    finally:
        conn.close()


def metrics(start: str, end: str) -> dict:
    """统计 [start, end] 闭区间的核心指标"""
    row = q("""
        SELECT COUNT(*),
               SUM(CASE WHEN order_status='delivered' THEN 1 ELSE 0 END),
               SUM(CASE WHEN order_status='delivered' THEN gmv ELSE 0 END),
               SUM(CASE WHEN order_status='delivered' AND is_late=1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN order_status='delivered' AND review_score<=2 THEN 1 ELSE 0 END),
               SUM(CASE WHEN order_status='delivered' AND review_score IS NOT NULL THEN 1 ELSE 0 END)
        FROM order_fact WHERE order_date BETWEEN ? AND ?
    """, (start, end))
    orders, dlv, gmv, late, bad, rated = row
    dlv, gmv, late, bad, rated = dlv or 0, gmv or 0, late or 0, bad or 0, rated or 0
    return {
        "下单量": orders or 0,
        "履约量": dlv,
        "GMV": gmv,
        "AOV": (gmv / dlv) if dlv else 0,
        "迟到率": (100.0 * late / dlv) if dlv else 0,
        "差评率": (100.0 * bad / rated) if rated else 0,
    }


def gate_status() -> str:
    """跑 qc_gate 取门禁结论，失败时如实说明"""
    try:
        r = subprocess.run([sys.executable, os.path.join(BASE, "qc_gate.py")],
                           capture_output=True, text=True, timeout=300)
        for line in r.stdout.splitlines():
            if line.startswith("门禁结果:"):
                return line.replace("门禁结果:", "").strip().split()[0]
        return "未知（qc_gate 输出异常）"
    except Exception as e:
        return f"未执行（{e}）"


def main():
    if not os.path.exists(DB):
        print("未找到 olist.db，请先跑 python import_to_sqlite.py")
        return 1

    # 宽表是日报的数据底座，缺了就现建
    if not q("SELECT name FROM sqlite_master WHERE type='table' AND name='order_fact'"):
        print("未找到 order_fact，正在构建…")
        subprocess.run([sys.executable, os.path.join(BASE, "build_fact_table.py")], check=True)

    maxd = q("SELECT MAX(order_date) FROM order_fact")[0]
    if len(sys.argv) > 1:
        day = sys.argv[1]
    else:
        day = (date.fromisoformat(maxd) - timedelta(days=30)).isoformat()

    d = date.fromisoformat(day)
    cur_s, cur_e = (d - timedelta(days=6)).isoformat(), d.isoformat()
    pre_s, pre_e = (d - timedelta(days=13)).isoformat(), (d - timedelta(days=7)).isoformat()

    today = metrics(d.isoformat(), d.isoformat())
    cur7 = metrics(cur_s, cur_e)
    pre7 = metrics(pre_s, pre_e)

    def pct(a, b):
        return None if not b else 100.0 * (a - b) / b

    flags = []
    for k in ("GMV", "下单量", "AOV"):
        chg = pct(cur7[k], pre7[k])
        if chg is not None and abs(chg) > WARN_PCT:
            flags.append(f"{k} 近7日较前7日 {chg:+.1f}%（阈值 ±{WARN_PCT:.0f}%）")
    dlate = cur7["迟到率"] - pre7["迟到率"]
    if abs(dlate) > WARN_PP:
        flags.append(f"迟到率 近7日较前7日 {dlate:+.2f}pp（阈值 ±{WARN_PP:.0f}pp）")

    gate = gate_status()
    truncated = (date.fromisoformat(maxd) - d).days < 30

    L = []
    L.append(f"# 经营日报 · {day}\n")
    L.append(f"> 生成于 {date.today()}｜数据截止 {maxd}｜GMV 口径：已送达 + 含运费"
             f"（`price + freight_value`）｜质检门禁：**{gate}**\n")

    if truncated:
        L.append(f"> ⚠️ **数据未稳定**：该日期距数据截止仅 {(date.fromisoformat(maxd)-d).days} 天，"
                 f"送达状态可能尚未回写，结论仅供参考。\n")

    L.append("## 当日概览\n")
    L.append("| 指标 | 当日 |")
    L.append("|---|---|")
    L.append(f"| 下单量 | {today['下单量']:,} |")
    L.append(f"| 履约量（已送达） | {today['履约量']:,} |")
    L.append(f"| GMV | ¥{today['GMV']:,.0f} |")
    L.append(f"| 客单价 AOV | ¥{today['AOV']:,.2f} |")
    L.append(f"| 迟到率 | {today['迟到率']:.2f}% |")
    L.append(f"\n> 依据：`order_fact` 按 `order_date = {day}` 过滤，{today['下单量']} 行｜"
             f"已送达口径 + 含运费")

    L.append(f"\n## 近 7 日 vs 前 7 日（异动判定）\n")
    L.append(f"窗口：{cur_s} ~ {cur_e}　对比　{pre_s} ~ {pre_e}\n")
    L.append("| 指标 | 近 7 日 | 前 7 日 | 变化 | 判定 |")
    L.append("|---|---|---|---|---|")
    for k, fmt in (("GMV", "¥{:,.0f}"), ("下单量", "{:,}"), ("AOV", "¥{:,.2f}")):
        chg = pct(cur7[k], pre7[k])
        chg_s = f"{chg:+.1f}%" if chg is not None else "—"
        hit = chg is not None and abs(chg) > WARN_PCT
        L.append(f"| {k} | {fmt.format(cur7[k])} | {fmt.format(pre7[k])} | {chg_s} | {'⚠️ 异动' if hit else '正常'} |")
    dlt = cur7["迟到率"] - pre7["迟到率"]
    L.append(f"| 迟到率 | {cur7['迟到率']:.2f}% | {pre7['迟到率']:.2f}% | {dlt:+.2f}pp "
             f"| {'⚠️ 异动' if abs(dlt) > WARN_PP else '正常'} |")
    bchg = pct(cur7["差评率"], pre7["差评率"])
    L.append(f"| 差评率 | {cur7['差评率']:.2f}% | {pre7['差评率']:.2f}% "
             f"| {f'{bchg:+.1f}%' if bchg is not None else '—'} | 参考值 |")
    L.append(f"\n> 依据：近 7 日 {cur_s} ~ {cur_e}（{cur7['下单量']} 行）对比前 7 日 "
             f"{pre_s} ~ {pre_e}（{pre7['下单量']} 行）｜迟到率、差评率均以已送达订单为分母")

    L.append("\n## 结论与动作\n")
    if flags:
        L.append("**触发异动：**\n")
        for f in flags:
            L.append(f"- {f}")
        L.append("\n**按归因 SOP 处理：**\n")
        L.append("1. S1 先排除数据问题 —— 门禁为 "
                 f"`{gate}`；若为 WARN/BLOCK，先确认不是口径或回写延迟导致\n"
                 "2. S2 量化现象 —— 定位到具体品类 / 地区 / 渠道\n"
                 "3. S3 量价拆解 —— 是单量在跌还是客单价在跌\n"
                 "4. 根因结论需**主因占比过半**才可写进结论，避免伪相关\n")
    else:
        L.append("近 7 日各项指标均在阈值内，无需专项归因。\n")

    L.append("\n## 数据说明\n")
    L.append(f"- GMV 只含 `order_status='delivered'`，含运费；与全部历史报表一致，不得改用其他口径")
    L.append(f"- 差评率分母为「已送达且已有评价」订单，评价有滞后，日粒度会低估，故不用于当日结论")
    L.append(f"- 门禁明细：`python qc_gate.py`")

    md = "\n".join(L) + "\n"
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"daily_{day}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    print(md)
    print(f"\n已写入 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
