-- ============================================================
-- 模块 01：交易总览 — 月度 GMV / 订单量 / 客单价(AOV)
-- ============================================================
-- 【业务问题】生意做得怎么样？涨了还是跌了？
-- 【口径说明】
--   1. 只统计 order_status = 'delivered'（成交口径，见质检报告坑5）
--   2. GMV = price + freight_value（商品价 + 运费）
--   3. order_items 是行级表：一单多商品会有多行，
--      所以订单数必须 COUNT(DISTINCT order_id)，不能 COUNT(*)
-- 【SQL 考点】strftime 日期截断 · 多表 JOIN · DISTINCT 计数 · GROUP BY
-- 【业务解读怎么写】看 2018 年月度 GMV 是否还在增长；
--   AOV 突然跳变通常是大促或品类结构变化，值得下钻。
-- ============================================================

SELECT
    strftime('%Y-%m', o.order_purchase_timestamp) AS year_month,   -- 考点：日期截成"年-月"
    COUNT(DISTINCT o.order_id)                    AS orders,       -- 订单数（去重！）
    ROUND(SUM(oi.price + oi.freight_value), 2)    AS gmv,          -- 月度 GMV
    ROUND(SUM(oi.price + oi.freight_value)
        / COUNT(DISTINCT o.order_id), 2)          AS aov           -- 客单价 = GMV / 订单数
FROM olist_orders o
JOIN olist_order_items oi
    ON oi.order_id = o.order_id
WHERE o.order_status = 'delivered'
GROUP BY 1          -- 按第一个 SELECT 列分组（year_month）
ORDER BY 1;         -- 时间升序

-- 【预期结果】2016-09 ~ 2018-10 共 26 个月；
--   2016 年底只有几十单（冷启动），正式分析从 2017-01 开始看。
-- 【下一步】把结果导出画折线图 → output/01_gmv_trend.png
