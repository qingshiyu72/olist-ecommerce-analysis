-- ============================================================
-- 模块 04：RFM 客户分层
-- ============================================================
-- 【业务问题】谁是最有价值的客户？谁正在流失？
--   R = Recency（最近一次购买距今多久）F = Frequency（买了几单）M = Monetary（花了多少钱）
-- 【口径说明（重要）】
--   1. 按 customer_unique_id 聚合（"人"级）！customer_id 是"人×单"级（见质检坑6）
--   2. 参照日 = 数据集内最大下单日 '2018-10-17'，不要用今天——
--      否则所有人都"很久没买"，R 全部失真
-- 【业务解读】R 高 F 高 = Champions；R 高(久未购) F 高 = "高价值流失预警"，
--   这群人是最该被营销召回的——这就是分层指导动作。
-- ============================================================

WITH order_value AS (
    -- 1) 每笔订单的金额（行级 → 单级）
    SELECT
        o.order_id,
        o.customer_id,
        o.order_purchase_timestamp      AS ts,
        SUM(oi.price + oi.freight_value) AS monetary
    FROM olist_orders o
    JOIN olist_order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status = 'delivered'
    GROUP BY o.order_id, o.customer_id
),
rfm AS (
    -- 2) 单级 → 人级（customer_unique_id），同时算出 R / F / M
    SELECT
        c.customer_unique_id,
        CAST(julianday('2018-10-17')
           - julianday(MAX(v.ts)) AS INT)        AS recency_days,   -- R：距今天数
        COUNT(DISTINCT v.order_id)               AS frequency,      -- F：订单数
        ROUND(SUM(v.monetary), 2)                AS monetary        -- M：累计消费
    FROM order_value v
    JOIN olist_customers c ON c.customer_id = v.customer_id
    GROUP BY c.customer_unique_id
),
scored AS (
    -- 3) NTILE(5)：按顺序切成 5 等份打 1~5 分
    SELECT *,
        NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,  -- DESC：越近(天数越小)排越前 = 分越高
        NTILE(5) OVER (ORDER BY frequency)         AS f_score,  -- 买得多 = 分高
        NTILE(5) OVER (ORDER BY monetary)          AS m_score   -- 花得多 = 分高
    FROM rfm
)
-- 4) 汇总：每个 R/F/M 组合有多少人（也可在此加 CASE 打分层标签）
SELECT
    r_score, f_score, m_score,
    COUNT(*)               AS users,
    ROUND(AVG(monetary),2) AS avg_monetary
FROM scored
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 2 DESC, 3 DESC;

-- 【预期结果】总客户数 ≈ 93,000+（注意比 99,441 少——因为同人多单被合并了，
--   这本身就是复购存在的证据）；绝大多数客户 F=1（巴西电商一次性购买为主）。
-- 【方法边界】F=1 客户占比 >95% 时，RFM 的 F 轴区分度有限，
--   分层主要由 R、M 两轴驱动；这是平台型电商一次性购买结构决定的。
