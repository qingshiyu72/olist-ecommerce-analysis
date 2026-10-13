-- ============================================================
-- 模块 11：P3-3 假设验证 — 排除法收网：新客见顶 vs 体验恶化
-- ============================================================
-- 【业务问题】两个候选假设：
--   A. 体验恶化吓跑客户（履约变慢/迟到变多）
--   B. 获客见顶（新客盘子不再扩大，3% 复购接不了棒）
-- 【方法】归因 = 排除法的艺术：先验最直觉的 A（成本最低），再证 B
-- 【工程优化】同模块 09：首单月物化为 TEMP TABLE + 索引
-- 【面试追问预演】"怎么排除 A？"→ 用 07/08 的现成指标做年度对比，
--   若 2018 履约/评分不差于 2017，A 不成立。
-- ============================================================

-- ---------- 假设 A：体验恶化了吗？（2017 vs 2018 履约对比） ----------
SELECT
    strftime('%Y', o.order_purchase_timestamp)                            AS yr,
    ROUND(AVG(julianday(o.order_delivered_customer_date)
        - julianday(o.order_purchase_timestamp)), 2)                      AS avg_total_days,
    ROUND(100.0 * SUM(CASE
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN 1 ELSE 0 END) / COUNT(*), 2)                                 AS late_rate_pct,
    ROUND(AVG(r.review_score), 2)                                         AS avg_review_score
FROM olist_orders o
JOIN (
    SELECT order_id, review_score,
           ROW_NUMBER() OVER (PARTITION BY order_id
               ORDER BY review_answer_timestamp DESC) AS rn
    FROM olist_order_reviews
) r ON r.order_id = o.order_id AND r.rn = 1
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_purchase_timestamp >= '2017-01-01'
GROUP BY 1
ORDER BY 1;

-- ---------- 假设 B：新客见顶了吗？（月度获客曲线） ----------
DROP TABLE IF EXISTS tmp_first_order;
CREATE TEMP TABLE tmp_first_order AS
SELECT
    c.customer_unique_id,
    MIN(strftime('%Y-%m', o.order_purchase_timestamp)) AS cohort_month
FROM olist_orders o
JOIN olist_customers c ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
GROUP BY 1;
CREATE INDEX idx_tfo_uid ON tmp_first_order(customer_unique_id);

SELECT
    cohort_month,
    COUNT(*)                                     AS new_customers,
    SUM(COUNT(*)) OVER (ORDER BY cohort_month)   AS cum_customers
FROM tmp_first_order
WHERE cohort_month >= '2017-01'
GROUP BY 1
ORDER BY 1;
