# -*- coding: utf-8 -*-
"""
L2 清洗层：把 9 张业务表合并成一张订单宽表 order_fact（一单一行的分析底座）。

做的事：
  1. 多源合并 —— orders / order_items / customers / payments / reviews 拼成一行一单
  2. 一对多归一 —— items、payments 先按 order_id 聚合，避免 JOIN 行膨胀（GMV 被放大的坑）
  3. 重复清洗 —— 评价按 order_id 保留最新一条
  4. 异常标记 —— 零元支付、负值、缺履约时间，打标而不丢弃（可追溯）
  5. 派生字段 —— order_date、days_to_deliver、is_late、gmv（含运费）

用法: python build_fact_table.py
幂等: 每次重建 order_fact，不修改任何原始表
"""
import os
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "olist.db")

DDL = """
DROP TABLE IF EXISTS order_fact;

CREATE TABLE order_fact AS
WITH items AS (
    -- 订单明细是一对多：先聚合回订单级，否则 GMV 会被放大
    SELECT order_id,
           SUM(price)                          AS item_value,
           SUM(freight_value)                  AS freight_value,
           COUNT(*)                            AS item_cnt
    FROM olist_order_items GROUP BY order_id
),
pays AS (
    -- 支付同样一对多（分期/多方式）
    SELECT order_id,
           SUM(payment_value)                  AS pay_value,
           COUNT(*)                            AS pay_cnt,
           GROUP_CONCAT(DISTINCT payment_type) AS pay_types
    FROM olist_order_payments GROUP BY order_id
),
rev AS (
    -- 重复清洗：同一订单多条评价，只保留最新一条
    SELECT order_id, review_score
    FROM (SELECT order_id, review_score,
                 ROW_NUMBER() OVER (PARTITION BY order_id
                                    ORDER BY review_answer_timestamp DESC) rn
          FROM olist_order_reviews)
    WHERE rn = 1
)
SELECT
    o.order_id,
    date(o.order_purchase_timestamp)                          AS order_date,
    strftime('%Y-%m', o.order_purchase_timestamp)             AS order_month,
    o.order_status,
    c.customer_unique_id,
    c.customer_state,
    i.item_value,
    i.freight_value,
    ROUND(COALESCE(i.item_value, 0) + COALESCE(i.freight_value, 0), 2) AS gmv,
    i.item_cnt,
    p.pay_value,
    p.pay_types,
    ROUND(julianday(o.order_delivered_customer_date)
          - julianday(o.order_purchase_timestamp), 2)         AS days_to_deliver,
    CASE WHEN o.order_delivered_customer_date IS NOT NULL
          AND o.order_delivered_customer_date > o.order_estimated_delivery_date
         THEN 1 ELSE 0 END                                    AS is_late,
    r.review_score,
    -- 异常标记：打标不丢弃，保证可追溯
    CASE WHEN p.pay_value IS NULL THEN 1 ELSE 0 END           AS flag_no_payment,
    CASE WHEN p.pay_value = 0 THEN 1 ELSE 0 END               AS flag_zero_payment,
    CASE WHEN p.pay_value < 0 THEN 1 ELSE 0 END               AS flag_negative_payment,
    CASE WHEN o.order_status = 'delivered'
          AND o.order_delivered_customer_date IS NULL
         THEN 1 ELSE 0 END                                    AS flag_missing_delivery
FROM olist_orders o
LEFT JOIN items  i ON i.order_id = o.order_id
LEFT JOIN pays   p ON p.order_id = o.order_id
LEFT JOIN rev    r ON r.order_id = o.order_id
LEFT JOIN olist_customers c ON c.customer_id = o.customer_id;

CREATE INDEX IF NOT EXISTS idx_fact_date ON order_fact(order_date);
CREATE INDEX IF NOT EXISTS idx_fact_uid  ON order_fact(customer_unique_id);
"""


def main():
    if not os.path.exists(DB):
        print(f"未找到数据库 {DB}，请先跑 python import_to_sqlite.py")
        return 1

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    before = cur.execute("SELECT COUNT(*) FROM olist_orders").fetchone()[0]
    cur.executescript(DDL)
    conn.commit()

    after, n_null_gmv, n_zero, n_neg, n_miss = cur.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN gmv IS NULL THEN 1 ELSE 0 END),
               SUM(flag_zero_payment),
               SUM(flag_negative_payment),
               SUM(flag_missing_delivery)
        FROM order_fact""").fetchone()

    print("=" * 66)
    print("L2 清洗层 · 订单宽表 order_fact")
    print("=" * 66)
    print(f"  源订单数          {before:>8,}")
    print(f"  宽表行数          {after:>8,}   {'（一单一行，无膨胀）' if before == after else '⚠️ 行数不一致！'}")
    print(f"  GMV 为空（无明细） {n_null_gmv or 0:>8,}")
    print(f"  零元支付          {n_zero or 0:>8,}")
    print(f"  负值支付          {n_neg or 0:>8,}")
    print(f"  delivered 缺签收时间 {n_miss or 0:>6,}")
    print("\n  已建索引: idx_fact_date / idx_fact_uid")
    print("  原始表未被修改，可随时重建")
    print("=" * 66)

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
