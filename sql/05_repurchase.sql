-- ============================================================
-- 模块 05：复购分析 — 平台的健康度指标
-- ============================================================
-- 【业务问题】多少比例的客户会回来买第二次？
-- 【口径说明】复购率按 customer_unique_id 口径（见质检坑6）：
--   复购率 = 下单 ≥2 次的客户数 / 总客户数
-- 【业务解读】Olist 这类平台复购率天然偏低（平台型电商），
--   报告里要和行业常识对照着讲，别把它当异常。
-- ============================================================

WITH cust_orders AS (
    -- 每个"真人"下过几单
    SELECT
        c.customer_unique_id,
        COUNT(DISTINCT o.order_id) AS order_cnt
    FROM olist_orders o
    JOIN olist_customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1
)
SELECT
    COUNT(*)                                                        AS total_customers,
    SUM(CASE WHEN order_cnt >= 2 THEN 1 ELSE 0 END)                 AS repeat_customers,
    ROUND(100.0 * SUM(CASE WHEN order_cnt >= 2 THEN 1 ELSE 0 END)
        / COUNT(*), 2)                                              AS repeat_rate_pct
FROM cust_orders;

-- 【预期结果】复购率大约在 3% 上下——低是正常的，解释原因比数字本身重要。
