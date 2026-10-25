-- ============================================================
-- 模块 08：口碑洞察 — 评分分布 × 物流时长交叉验证
-- ============================================================
-- 【业务问题】低分订单是不是物流慢造成的？（验证模块 07 留下的假设）
-- 【口径说明（重要）】reviews 有重复（质检坑2）：
--   用 ROW_NUMBER() 每单只保留 review_answer_timestamp 最新的一条
-- 【实现说明】ROW_NUMBER() OVER (PARTITION BY ...) 去重，
--   Step 2 的 Agent 取数工具库也封装了同样的逻辑
-- 【业务解读】如果 1~2 分订单的平均配送时长明显高于 5 分订单，
--   就得到"物流体验拖累口碑"的证据链；注意措辞是"相关"不是"因果"。
-- ============================================================

WITH latest_review AS (
    -- 去重：每单只留最新评价
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY r.order_id
            ORDER BY r.review_answer_timestamp DESC
        ) AS rn
    FROM olist_order_reviews r
),
lr AS (
    SELECT order_id, review_score
    FROM latest_review
    WHERE rn = 1
)
SELECT
    lr.review_score,
    COUNT(*)                     AS orders,
    ROUND(100.0 * COUNT(*)
        / SUM(COUNT(*)) OVER (), 2)                              AS score_share_pct,
    ROUND(AVG(julianday(o.order_delivered_customer_date)
        - julianday(o.order_delivered_carrier_date)), 2)         AS avg_shipping_days,
    ROUND(100.0 * SUM(CASE
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN 1 ELSE 0 END) / COUNT(*), 2)                        AS late_rate_pct
FROM lr
JOIN olist_orders o ON o.order_id = lr.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_delivered_carrier_date  IS NOT NULL
GROUP BY 1
ORDER BY 1;

-- 【预期结果】5 分占一半以上；1~2 分订单的 avg_shipping_days 和 late_rate
--   应显著高于 4~5 分——这就是"物流 → 口碑"的证据
-- 【下一步】把每个评分档的差评文本抽 20 条给 LLM 做归因（P4 的种子任务）
