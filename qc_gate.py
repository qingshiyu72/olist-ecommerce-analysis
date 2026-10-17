# -*- coding: utf-8 -*-
"""
数据质检门禁（qc_gate）：跑 8 项检查，输出 READY / WARN / BLOCK。
用法:
    python qc_gate.py          # 跑全部检查
退出码: 0=READY  1=WARN  2=BLOCK  （可直接接入跑批，非 READY 则中断发报）

说明:
- 门禁项（参与判定）: 唯一性 / 完整性 / 一致性 / 时效 / 异常值
- 信息项（恒定的结构性属性，只报告不阻塞）: 维度表冗余、主键粒度、GMV 口径差额
  理由：这三项是数据集固有属性，处理方式已固化在分析层。若把它们纳入门禁，
  每次都会触发 WARN，门禁就失去意义——门禁要抓的是"本批数据的异常"。
"""
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "olist.db")

# 本项目 GMV 口径：含运费（price + freight_value），与全部历史报表一致
GMV_INCLUDE_FREIGHT = True


def q1(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchone()[0]


def level(v, warn, block, higher_is_worse=True):
    """按阈值返回等级"""
    if higher_is_worse:
        if block is not None and v >= block:
            return "BLOCK"
        if warn is not None and v >= warn:
            return "WARN"
    else:
        if block is not None and v <= block:
            return "BLOCK"
        if warn is not None and v <= warn:
            return "WARN"
    return "READY"


def main():
    if not os.path.exists(DB):
        print(f"未找到数据库 {DB}，请先跑 python import_to_sqlite.py")
        return 2

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    ref = q1(cur, "SELECT MAX(order_purchase_timestamp) FROM olist_orders")[:10]
    print("=" * 78)
    print(f"数据质检门禁 · olist.db")
    print(f"参照日（数据内最新下单日）: {ref}   GMV 口径: 含运费(price+freight_value)")
    print("=" * 78)

    gate, info = [], []          # (编号, 维度, 检查项, 实测值, 等级/说明)

    # ---- QC-01 唯一性：同一订单多条评价（分析层 PARTITION BY order_id，故用订单口径）----
    rows, uniq_rid, uniq_oid = cur.execute(
        "SELECT COUNT(*), COUNT(DISTINCT review_id), COUNT(DISTINCT order_id) "
        "FROM olist_order_reviews").fetchone()
    dup, dup_pct = rows - uniq_oid, 100.0 * (rows - uniq_oid) / rows
    gate.append(("QC-01", "唯一性", "同一订单多条评价", f"{dup} 单 ({dup_pct:.2f}%)",
                 level(dup_pct, 0.1, 1.0),
                 "按 review_creation_date 保留最新一条"))

    # ---- QC-04 完整性：履约时间字段缺失 ----
    miss = q1(cur, """SELECT 100.0*SUM(CASE WHEN order_delivered_customer_date IS NULL
                    THEN 1 ELSE 0 END)/COUNT(*) FROM olist_orders
                    WHERE order_status='delivered'""")
    gate.append(("QC-04", "完整性", "履约时间字段缺失", f"缺失率 {miss:.2f}%",
                 level(miss, 2.0, 5.0), "缺失订单排除出分母，缺失率写入日报"))

    # ---- QC-05 一致性：支付记录找不到对应订单 ----
    orphan = q1(cur, """SELECT COUNT(DISTINCT p.order_id) FROM olist_order_payments p
                        LEFT JOIN olist_orders o ON o.order_id=p.order_id
                        WHERE o.order_id IS NULL""")
    total_pay_orders = q1(cur, "SELECT COUNT(DISTINCT order_id) FROM olist_order_payments")
    orphan_pct = 100.0 * orphan / total_pay_orders
    gate.append(("QC-05", "一致性", "支付记录无对应订单", f"{orphan} 单 ({orphan_pct:.3f}%)",
                 level(orphan_pct, 0.5, None), "以 orders 为准，孤儿支付单单独输出"))

    # ---- QC-07 时效：近期数据是否完整（截尾检测）----
    overall = q1(cur, """SELECT 100.0*SUM(CASE WHEN order_status='delivered' THEN 1 ELSE 0 END)
                         /COUNT(*) FROM olist_orders""")
    recent = q1(cur, """SELECT 100.0*SUM(CASE WHEN order_status='delivered' THEN 1 ELSE 0 END)
                        /COUNT(*) FROM olist_orders
                        WHERE julianday(?) - julianday(order_purchase_timestamp) <= 30""",
                (ref,))
    gap = overall - recent
    gate.append(("QC-07", "时效", "近期数据完整性(截尾)", f"近30天送达率 {recent:.1f}% vs 全期 {overall:.1f}%",
                 level(gap, 3.0, None), "趋势结论只用 T-30 之前的数据，末尾月份标注'采集未完整'"))

    # ---- QC-08 异常值：支付金额负值 / 零值 / 极值 ----
    neg, zero, extreme = cur.execute("""
        WITH t AS (SELECT payment_value,
                          ROW_NUMBER() OVER (ORDER BY payment_value) rn,
                          COUNT(*) OVER () n
                   FROM olist_order_payments)
        SELECT SUM(CASE WHEN payment_value < 0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN payment_value = 0 THEN 1 ELSE 0 END),
               SUM(CASE WHEN rn > n*0.999 THEN 1 ELSE 0 END) FROM t""").fetchone()
    gate.append(("QC-08", "异常值", "支付金额负值/零值",
                 f"负值 {neg} 条，零值 {zero} 条，P99.9 以上 {extreme} 条",
                 "BLOCK" if neg > 0 else ("WARN" if zero > 0 else "READY"),
                 "负值一律剔除；零值(voucher/未定义)标记后剔除"))

    # ---- 信息项（不参与门禁）----
    info.append(("QC-01b", "唯一性", "重复 review_id", f"{rows - uniq_rid} 条",
                 "与订单级口径不同，勿与前一项混用"))

    per_prefix = q1(cur, """SELECT 1.0*COUNT(*)/COUNT(DISTINCT geolocation_zip_code_prefix)
                            FROM olist_geolocation""")
    info.append(("QC-02", "粒度", "维度表冗余(地理)", f"{per_prefix:.1f} 行/前缀",
                 "已知属性，关联前必须去重"))

    cid, cuid = cur.execute(
        "SELECT COUNT(DISTINCT customer_id), COUNT(DISTINCT customer_unique_id) "
        "FROM olist_customers").fetchone()
    info.append(("QC-03", "粒度", "主键粒度歧义", f"customer_id {cid:,} vs unique_id {cuid:,}",
                 "分析层已统一用 customer_unique_id"))

    incl = q1(cur, """SELECT SUM(oi.price + oi.freight_value) FROM olist_orders o
                      JOIN olist_order_items oi ON oi.order_id=o.order_id
                      WHERE o.order_status='delivered'""")
    excl = q1(cur, """SELECT SUM(oi.price) FROM olist_orders o
                      JOIN olist_order_items oi ON oi.order_id=o.order_id
                      WHERE o.order_status='delivered'""")
    info.append(("QC-06", "一致性", "GMV 口径差额", f"含运费 {incl:,.0f} vs 不含 {excl:,.0f} "
                 f"(差 {100.0*(incl-excl)/incl:.2f}%)",
                 "本项目固定含运费，与历史报表一致"))

    # ---- 输出 ----
    print("\n【门禁项】")
    for cid_, dim, name, val, lv, act in gate:
        print(f"  {cid_} {dim}/{name:<16} {val:<34} {lv:<6} → {act}")

    print("\n【信息项 · 只报告不阻塞】")
    for cid_, dim, name, val, note in info:
        print(f"  {cid_} {dim}/{name:<16} {val:<34} {note}")

    levels = [g[4] for g in gate]
    final = "BLOCK" if "BLOCK" in levels else ("WARN" if "WARN" in levels else "READY")
    print("\n" + "=" * 78)
    print(f"门禁结果: {final}   " + {
        "READY": "全部通过，可发布日报与看板",
        "WARN": "可发布，但日报必须带质检脚注并说明原因",
        "BLOCK": "停止出数，先修复再发布",
    }[final])
    print("=" * 78)

    conn.close()
    return {"READY": 0, "WARN": 1, "BLOCK": 2}[final]


if __name__ == "__main__":
    sys.exit(main())
