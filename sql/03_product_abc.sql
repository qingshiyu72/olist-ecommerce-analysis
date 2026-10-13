-- ============================================================
-- 模块 03：商品结构 — 品类 Top 榜 + ABC/帕累托分析
-- ============================================================
-- 【业务问题】钱主要从哪些品类来？头部集中度多高？
-- 【口径说明】COALESCE 优先用英文品类名，翻译表没有的回退葡语原名
-- 【SQL 考点】CTE(WITH) · 窗口函数 SUM() OVER / ROW_NUMBER() · LEFT JOIN
--   累计占比是 ABC 分析的灵魂：A 类 = 累计贡献 ≤80% 的品类
-- 【业务解读怎么写】"health_beauty 等 X 个品类贡献了 80% 收入"
--   —— 这就是帕累托（二八法则）的量化表达。
-- ============================================================

WITH cat_sales AS (
    -- 1) 每个品类的收入（只算成交订单）
    SELECT
        COALESCE(t.product_category_name_english,
                 p.product_category_name)              AS category,   -- 翻译缺失时回退
        SUM(oi.price)                                  AS revenue
    FROM olist_order_items oi
    JOIN olist_products p
        ON p.product_id = oi.product_id
    LEFT JOIN product_category_name_translation t       -- LEFT JOIN：翻译表没有的不能丢
        ON t.product_category_name = p.product_category_name
    JOIN olist_orders o
        ON o.order_id = oi.order_id
       AND o.order_status = 'delivered'
    GROUP BY 1
),
ranked AS (
    -- 2) 排名 + 占比 + 累计占比（窗口函数一次算完）
    SELECT
        category,
        revenue,
        ROUND(100.0 * revenue
            / SUM(revenue) OVER (), 2)                          AS rev_share_pct,
        ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC)
            / SUM(revenue) OVER (), 2)                          AS cum_share_pct,  -- 累计占比
        ROW_NUMBER() OVER (ORDER BY revenue DESC)               AS rn
    FROM cat_sales
)
SELECT
    rn,
    category,
    ROUND(revenue, 2)  AS revenue,
    rev_share_pct,
    cum_share_pct,
    CASE
        WHEN cum_share_pct <= 80 THEN 'A'    -- 头部：累计 ≤80% 收入
        WHEN cum_share_pct <= 95 THEN 'B'    -- 腰部
        ELSE 'C'                             -- 长尾
    END AS abc_class
FROM ranked
ORDER BY rn
LIMIT 15;        -- 先看 Top15，完整 73 行可去掉 LIMIT 导出

-- 【预期结果】Top1 应为 health_beauty / watches_gifts / bed_bath_table 一档
-- 【知识点】SUM(revenue) OVER (ORDER BY revenue DESC) = "滚动累计"，
--   这是窗口函数最实用的形态之一，Step 2 的 Agent 也会直接复用这段。
