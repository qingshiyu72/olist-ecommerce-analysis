-- ============================================================
-- 模块 10：P3-2 维度下钻 — 2018H1 vs 2017H1，谁在拖后腿？
-- ============================================================
-- 【业务问题】增速放缓是全面性的，还是某个品类/地域掉的？（切片定位）
-- 【口径说明】同口径对比两个半年（H1 vs H1），消除季节性干扰
-- 【方法说明】比 H1 vs H1 而非同比逐月：半年聚合降噪（单月波动大），
--   且 H1 对 H1 排除黑五/圣诞等季节因素。
-- ============================================================

WITH period_cat AS (
    -- 每个品类在两个半年的 GMV
    SELECT
        CASE
            WHEN strftime('%Y-%m', o.order_purchase_timestamp) BETWEEN '2017-01' AND '2017-06' THEN '2017H1'
            WHEN strftime('%Y-%m', o.order_purchase_timestamp) BETWEEN '2018-01' AND '2018-06' THEN '2018H1'
        END                                                              AS period,
        COALESCE(t.product_category_name_english,
                 p.product_category_name)                                AS category,
        SUM(oi.price + oi.freight_value)                                 AS gmv
    FROM olist_orders o
    JOIN olist_order_items oi ON oi.order_id = o.order_id
    JOIN olist_products p     ON p.product_id = oi.product_id
    LEFT JOIN product_category_name_translation t
        ON t.product_category_name = p.product_category_name
    WHERE o.order_status = 'delivered'
    GROUP BY 1, 2
)
SELECT
    category,
    ROUND(COALESCE(SUM(CASE WHEN period = '2017H1' THEN gmv END), 0), 2) AS gmv_2017h1,
    ROUND(COALESCE(SUM(CASE WHEN period = '2018H1' THEN gmv END), 0), 2) AS gmv_2018h1,
    ROUND(100.0 * (SUM(CASE WHEN period = '2018H1' THEN gmv END)
        - SUM(CASE WHEN period = '2017H1' THEN gmv END))
        / SUM(CASE WHEN period = '2017H1' THEN gmv END), 1)              AS yoy_pct,
    ROUND(SUM(CASE WHEN period = '2018H1' THEN gmv END)
        - SUM(CASE WHEN period = '2017H1' THEN gmv END), 2)              AS gmv_gap
FROM period_cat
WHERE period IS NOT NULL
GROUP BY 1
HAVING SUM(CASE WHEN period = '2018H1' THEN gmv END) > 50000    -- 门槛：排除小品类噪音
   AND SUM(CASE WHEN period = '2017H1' THEN gmv END) > 0        -- 2017 没有的新品类无同比意义
ORDER BY gmv_gap ASC        -- 掉得最狠的排最前
LIMIT 15;

-- 【预期结论】绝大多数品类 2018H1 仍在增长 → 说明不是品类结构恶化，
--   而是全域性放缓 → 把怀疑引向"获客端"（见模块 11）
