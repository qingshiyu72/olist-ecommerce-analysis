# -*- coding: utf-8 -*-
"""Olist 看板数据刷新脚本：从本地 olist.db 导出 7 张聚合 CSV 给 Power BI。
用法：python _build_data.py   （跑完后在 Power BI 里点"刷新"即可更新看板）
口径：与项目报告一致——KPI/月度取自 order_fact（清洗后的事实表），剔除已取消订单。"""
import sqlite3, csv, os

DB  = os.path.join(os.path.dirname(__file__), '..', 'olist.db')
OUT = os.path.dirname(__file__)
con = sqlite3.connect(DB)
cur = con.cursor()

def dump(sql, fname):
    rows = cur.execute(sql).fetchall()
    cols = [d[0] for d in cur.description]
    with open(os.path.join(OUT, fname), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    print(fname, 'rows=', len(rows))

# 00 总览 KPI（单行，做卡片）
dump("""
SELECT (SELECT COUNT(DISTINCT order_id) FROM olist_orders) AS 总订单数,
       (SELECT ROUND(SUM(price+freight_value),0) FROM olist_order_items) AS 总GMV,
       (SELECT ROUND(100.0*(1-AVG(is_late)),1) FROM order_fact
         WHERE order_status='delivered' AND is_late IS NOT NULL) AS 整体准时率_pct,
       (SELECT ROUND(AVG(review_score),2) FROM olist_order_reviews) AS 整体平均评分,
       (SELECT COUNT(DISTINCT customer_unique_id) FROM olist_customers) AS 独立客户数
""", '00_总览KPI.csv')

# 01 月度经营 KPI（趋势图；剔除尾部稀疏月份）
dump("""
SELECT order_month AS 月份, COUNT(*) AS 订单量, ROUND(SUM(gmv),0) AS GMV,
       ROUND(AVG(days_to_deliver),1) AS 平均妥投天数,
       ROUND(100.0*SUM(CASE WHEN is_late=0 THEN 1 ELSE 0 END)/COUNT(is_late),1) AS 准时率_pct,
       ROUND(AVG(review_score),2) AS 平均评分
FROM order_fact WHERE order_status != 'canceled'
GROUP BY 月份 HAVING COUNT(*) >= 500 ORDER BY 月份
""", '01_月度经营KPI.csv')

# 02 履约延期分桶 × 评分（核心因果图）
dump("""
SELECT CASE WHEN diff <= -5 THEN '提前5天以上' WHEN diff <= -2 THEN '提前2-4天'
            WHEN diff < 0 THEN '提前0-1天'   WHEN diff = 0 THEN '踩点准时'
            WHEN diff <= 2 THEN '延期1-2天'  WHEN diff <= 5 THEN '延期3-5天'
            ELSE '延期5天以上' END AS 延期分桶,
       CASE WHEN diff <= -5 THEN 1 WHEN diff <= -2 THEN 2 WHEN diff < 0 THEN 3
            WHEN diff = 0 THEN 4 WHEN diff <= 2 THEN 5 WHEN diff <= 5 THEN 6
            ELSE 7 END AS 排序号,
       COUNT(*) AS 订单量, ROUND(AVG(review_score),2) AS 平均评分,
       ROUND(100.0*SUM(CASE WHEN review_score<=2 THEN 1 ELSE 0 END)/COUNT(*),1) AS 差评率_pct
FROM (SELECT julianday(o.order_delivered_customer_date)-julianday(o.order_estimated_delivery_date) AS diff,
             r.review_score
      FROM olist_orders o JOIN olist_order_reviews r ON r.order_id=o.order_id
      WHERE o.order_delivered_customer_date IS NOT NULL)
GROUP BY 延期分桶 ORDER BY 排序号
""", '02_履约延期与评分.csv')

# 03 品类 Top30
dump("""
SELECT COALESCE(t.product_category_name_english, p.product_category_name) AS 品类,
       COUNT(DISTINCT o.order_id) AS 订单量,
       ROUND(SUM(i.price+i.freight_value),0) AS 销售额,
       ROUND(AVG(r.review_score),2) AS 平均评分,
       ROUND(100.0*SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END)
             / SUM(CASE WHEN o.order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END),1) AS 延期率_pct
FROM olist_order_items i
JOIN olist_products p ON p.product_id = i.product_id
JOIN olist_orders o ON o.order_id = i.order_id
LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
LEFT JOIN olist_order_reviews r ON r.order_id = o.order_id
WHERE o.order_status != 'canceled'
GROUP BY 品类 ORDER BY 销售额 DESC LIMIT 30
""", '03_品类Top30.csv')

# 04 客户州分布
dump("""
SELECT c.customer_state AS 客户州, COUNT(DISTINCT o.order_id) AS 订单量,
       ROUND(SUM(i.price+i.freight_value),0) AS 销售额,
       ROUND(AVG(r.review_score),2) AS 平均评分,
       ROUND(100.0*SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END)
             / SUM(CASE WHEN o.order_delivered_customer_date IS NOT NULL THEN 1 ELSE 0 END),1) AS 延期率_pct
FROM olist_orders o
JOIN olist_customers c ON c.customer_id = o.customer_id
JOIN olist_order_items i ON i.order_id = o.order_id
LEFT JOIN olist_order_reviews r ON r.order_id = o.order_id
WHERE o.order_status != 'canceled'
GROUP BY 客户州 ORDER BY 销售额 DESC
""", '04_客户州分布.csv')

# 05 评分分布
dump("""
SELECT review_score AS 评分, COUNT(*) AS 评论数,
       ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM olist_order_reviews),1) AS 占比_pct
FROM olist_order_reviews GROUP BY 评分 ORDER BY 评分
""", '05_评分分布.csv')

# 06 支付方式
dump("""
SELECT CASE payment_type WHEN 'credit_card' THEN '信用卡' WHEN 'boleto' THEN '票据'
       WHEN 'voucher' THEN '优惠券' WHEN 'debit_card' THEN '借记卡' ELSE '未定义' END AS 支付方式,
       COUNT(DISTINCT order_id) AS 订单数, ROUND(SUM(payment_value),0) AS 支付金额
FROM olist_order_payments GROUP BY payment_type ORDER BY 支付金额 DESC
""", '06_支付方式.csv')
