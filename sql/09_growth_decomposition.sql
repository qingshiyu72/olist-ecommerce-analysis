-- ============================================================
-- 模块 09：P3-1 增长拆解 — GMV 为什么停在 100 万？
-- ============================================================
-- 【业务问题】2017 年月均增速 >20%，2018 年却原地踏步——先拆量价，再拆新旧客
-- 【工程优化】首单月表要和 9 万行订单表 JOIN，
--   直接用 CTE 在 SQLite 里会走低效查询计划（分钟级跑不完）。
--   解法：物化成 TEMP TABLE + 建索引 → 秒级。
--   教训：SQL 语法对 ≠ 跑得动，查询计划才是工程化的分水岭。
-- 【口径说明】用首单月定义新客：客户生命周期第一单所在月
--   = 获客月，之后所有订单都算存量贡献。
-- ============================================================

-- 1) 物化首单月表（获客月）并建索引
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

-- 2) 月度总览 + LAG 环比 + 新客/存量拆解，一张宽表收工
WITH monthly AS (
    SELECT
        strftime('%Y-%m', o.order_purchase_timestamp) AS ym,
        COUNT(DISTINCT o.order_id)                    AS orders,
        ROUND(SUM(oi.price + oi.freight_value), 2)    AS gmv,
        ROUND(SUM(oi.price + oi.freight_value)
            / COUNT(DISTINCT o.order_id), 2)          AS aov
    FROM olist_orders o
    JOIN olist_order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_purchase_timestamp >= '2017-01-01'
    GROUP BY 1
),
trend AS (
    SELECT
        ym, orders, gmv, aov,
        ROUND(100.0 * (gmv - LAG(gmv) OVER (ORDER BY ym))
            / LAG(gmv) OVER (ORDER BY ym), 1)          AS gmv_mom_pct
    FROM monthly
),
engine AS (
    SELECT
        strftime('%Y-%m', o.order_purchase_timestamp)              AS ym,
        CASE WHEN fo.cohort_month = strftime('%Y-%m', o.order_purchase_timestamp)
             THEN 'new' ELSE 'existing' END                        AS cust_type,
        SUM(oi.price + oi.freight_value)                           AS gmv
    FROM olist_orders o
    JOIN olist_customers c  ON c.customer_id = o.customer_id
    JOIN tmp_first_order fo ON fo.customer_unique_id = c.customer_unique_id
    JOIN olist_order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_purchase_timestamp >= '2017-01-01'
    GROUP BY 1, 2
)
SELECT
    t.ym,
    t.orders,
    t.gmv,
    t.gmv_mom_pct,
    t.aov,
    ROUND(MAX(CASE WHEN e.cust_type = 'new'      THEN e.gmv END), 2) AS gmv_new_cust,
    ROUND(MAX(CASE WHEN e.cust_type = 'existing' THEN e.gmv END), 2) AS gmv_existing,
    ROUND(100.0 * MAX(CASE WHEN e.cust_type = 'new' THEN e.gmv END)
        / t.gmv, 1)                                                  AS new_cust_gmv_pct
FROM trend t
JOIN engine e ON e.ym = t.ym
GROUP BY t.ym, t.orders, t.gmv, t.gmv_mom_pct, t.aov
ORDER BY t.ym;
