-- ============================================================
-- 模块 02：订单状态分布 — 流失在哪个环节
-- ============================================================
-- 【业务问题】下单的订单里，多少真正送达？多少被取消？
-- 【业务解读】canceled + unavailable 合计约 1.2%，
--   对平台是小钱，但对"取消率环比突然抬头"要敏感——那是体验恶化的信号。
-- ============================================================

-- 写法 A：基础版，GROUP BY + 占比
SELECT
    order_status,
    COUNT(*)                                              AS cnt,
    ROUND(100.0 * COUNT(*)
        / (SELECT COUNT(*) FROM olist_orders), 2)         AS pct   -- 标量子查询算总占比
FROM olist_orders
GROUP BY 1
ORDER BY cnt DESC;

-- 写法 B（备选）：SUM(CASE WHEN ...) 条件聚合，一行同时看"成交"和"未成交"的月度趋势
-- SELECT
--     strftime('%Y-%m', order_purchase_timestamp)              AS year_month,
--     SUM(CASE WHEN order_status = 'delivered'  THEN 1 ELSE 0 END) AS delivered_cnt,
--     SUM(CASE WHEN order_status = 'canceled'   THEN 1 ELSE 0 END) AS canceled_cnt,
--     SUM(CASE WHEN order_status = 'unavailable' THEN 1 ELSE 0 END) AS unavailable_cnt
-- FROM olist_orders
-- GROUP BY 1
-- ORDER BY 1;

-- 【预期结果】delivered ≈ 97.0%，canceled 625 单，unavailable 609 单
