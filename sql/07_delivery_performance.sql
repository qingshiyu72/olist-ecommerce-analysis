-- ============================================================
-- 模块 07：履约时效 — 物流是电商体验的命脉
-- ============================================================
-- 【业务问题】从下单到送达要几天？延迟交付比例多高？
-- 【口径说明】只看 delivered 且关键时间戳非空的订单；
--   SQLite 用 julianday() 算日期差（结果单位=天，小数）
-- 【SQL 考点】julianday 日期运算 · NULL 过滤 · 多指标一网打尽
-- 【业务解读怎么写】三个数分开讲：
--   handover（下单→发货）反映卖家/平台效率；
--   shipping（发货→送达）反映物流商效率；
--   late_rate（超预估送达）反映承诺管理——它是差评的头号嫌疑犯，
--   这个假设交给模块 08 验证。
-- ============================================================

SELECT
    ROUND(AVG(julianday(order_delivered_carrier_date)
            - julianday(order_purchase_timestamp)), 2)     AS avg_handover_days,   -- 下单→发货
    ROUND(AVG(julianday(order_delivered_customer_date)
            - julianday(order_delivered_carrier_date)), 2) AS avg_shipping_days,   -- 发货→送达
    ROUND(AVG(julianday(order_delivered_customer_date)
            - julianday(order_purchase_timestamp)), 2)     AS avg_total_days,      -- 下单→送达
    ROUND(100.0 * SUM(CASE
            WHEN order_delivered_customer_date > order_estimated_delivery_date
            THEN 1 ELSE 0 END) / COUNT(*), 2)              AS late_rate_pct        -- 超过承诺送达日的比例
FROM olist_orders
WHERE order_status = 'delivered'
  AND order_delivered_carrier_date   IS NOT NULL      -- NULL 不排除会污染 AVG
  AND order_delivered_customer_date  IS NOT NULL;

-- 【预期结果】总时长约 12 天上下（巴西物流就这么慢），late_rate 约 6~8%
-- 【进阶练习】按 customer_state 分组重复本查询 → 找出"又慢又常迟到"的州
