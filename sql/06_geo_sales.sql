-- ============================================================
-- 模块 06：地域分布 — 钱从哪些州来
-- ============================================================
-- 【业务问题】各州贡献多少 GMV？市场集中度如何？
-- 【口径说明（避坑）】
--   故意不用 geolocation 表！100 万行只有 1.9 万个 zip 前缀（质检坑3），
--   直接 JOIN 会让结果膨胀 50 倍。customers 表自带清洗好的 state 字段，又快又准。
-- 【SQL 考点】嵌套聚合：SUM(...) / SUM(SUM(...)) OVER () —— 分组占比的正确写法
--   （先 SUM 出每组的值，再对"组的和的SUM"开窗，注意两层括号）
-- 【业务解读怎么写】SP(圣保罗) 一州通常占 40% 左右，
--   结论写"市场高度集中于东南沿海"，再给一句业务含义：物流网络设计围绕 SP。
-- ============================================================

SELECT
    c.customer_state,
    COUNT(DISTINCT o.order_id)                          AS orders,
    ROUND(SUM(oi.price + oi.freight_value), 2)          AS gmv,
    ROUND(100.0 * SUM(oi.price + oi.freight_value)
        / SUM(SUM(oi.price + oi.freight_value)) OVER (),-- 嵌套聚合开窗：占比
        2)                                              AS gmv_share_pct
FROM olist_orders o
JOIN olist_order_items oi ON oi.order_id = o.order_id
JOIN olist_customers c    ON c.customer_id = o.customer_id
WHERE o.order_status = 'delivered'
GROUP BY 1
ORDER BY gmv DESC
LIMIT 10;

-- 【预期结果】SP >> RJ > MG > RS > PR ...，SP 单州约 40%+
-- 【进阶练习】把 LIMIT 10 去掉导出全量，用 map 画巴西地图（plotly choropleth）
