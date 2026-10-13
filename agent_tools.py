# -*- coding: utf-8 -*-
"""
Agent 工具库：把 olist.db 的 11 个分析模块封装成 LLM 可调用的函数。
每个函数 = 一个取数/分析能力，docstring 是 LLM 决定"用不用、怎么用"的依据。
口径与 sql/ 目录的模块严格一致（delivered 口径、customer_unique_id 人级）。
"""
import os
import sqlite3
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "olist.db")


def _run(sql: str) -> str:
    """执行 SQL（支持多语句：DDL + SELECT 混合），返回紧凑文本表格（LLM 友好）。"""
    conn = sqlite3.connect(DB)
    try:
        stmts = [s.strip() for s in sql.split(";") if s.strip()]
        df = None
        for s in stmts:
            if s.upper().startswith(("SELECT", "WITH")):
                df = pd.read_sql_query(s, conn)
            else:
                conn.execute(s)
        conn.commit()
        if df is None:
            return "（执行完成，无查询结果）"
        return df.to_string(index=False)
    finally:
        conn.close()


# ---------------- 1. 交易总览 ----------------

def get_monthly_gmv(start: str = "2017-01", end: str = "2018-08") -> str:
    """获取月度 GMV、订单量、客单价趋势（delivered 口径）。回答增长/趋势/波动类问题时必查。start/end 为 'YYYY-MM'。"""
    return _run(f"""
        SELECT strftime('%Y-%m', o.order_purchase_timestamp) AS ym,
               COUNT(DISTINCT o.order_id) AS orders,
               ROUND(SUM(oi.price + oi.freight_value), 2) AS gmv,
               ROUND(SUM(oi.price + oi.freight_value) / COUNT(DISTINCT o.order_id), 2) AS aov
        FROM olist_orders o
        JOIN olist_order_items oi ON oi.order_id = o.order_id
        WHERE o.order_status = 'delivered'
          AND strftime('%Y-%m', o.order_purchase_timestamp) BETWEEN '{start}' AND '{end}'
        GROUP BY 1 ORDER BY 1
    """)


# ---------------- 2. 订单状态 ----------------

def get_order_status() -> str:
    """获取订单状态分布与占比。回答履约健康、取消率类问题时使用。"""
    return _run("""
        SELECT order_status, COUNT(*) AS cnt,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM olist_orders), 2) AS pct
        FROM olist_orders GROUP BY 1 ORDER BY cnt DESC
    """)


# ---------------- 3. 商品结构 ----------------

def get_product_abc() -> str:
    """获取品类 ABC 分析（收入 Top 榜 + 累计占比 + ABC 分级）。回答品类结构/头部集中度问题时使用。"""
    return _run("""
        WITH cat_sales AS (
            SELECT COALESCE(t.product_category_name_english, p.product_category_name) AS category,
                   SUM(oi.price) AS revenue
            FROM olist_order_items oi
            JOIN olist_products p ON p.product_id = oi.product_id
            LEFT JOIN product_category_name_translation t
                ON t.product_category_name = p.product_category_name
            JOIN olist_orders o ON o.order_id = oi.order_id AND o.order_status = 'delivered'
            GROUP BY 1
        ),
        ranked AS (
            SELECT category, revenue,
                   ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS rev_share_pct,
                   ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC) / SUM(revenue) OVER (), 2) AS cum_share_pct,
                   ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rn
            FROM cat_sales
        )
        SELECT rn, category, ROUND(revenue, 2) AS revenue, rev_share_pct, cum_share_pct,
               CASE WHEN cum_share_pct <= 80 THEN 'A' WHEN cum_share_pct <= 95 THEN 'B' ELSE 'C' END AS abc_class
        FROM ranked ORDER BY rn LIMIT 15
    """)


# ---------------- 4. RFM 分层 ----------------

def get_rfm_summary() -> str:
    """获取 RFM 客户分层汇总（各 R/F/M 组合的用户数与平均消费，参照日 2018-10-17）。回答客户价值/分层问题时使用。"""
    return _run("""
        WITH order_value AS (
            SELECT o.order_id, o.customer_id, MAX(o.order_purchase_timestamp) AS ts,
                   SUM(oi.price + oi.freight_value) AS monetary
            FROM olist_orders o JOIN olist_order_items oi ON oi.order_id = o.order_id
            WHERE o.order_status = 'delivered' GROUP BY o.order_id, o.customer_id
        ),
        rfm AS (
            SELECT c.customer_unique_id,
                   CAST(julianday('2018-10-17') - julianday(MAX(v.ts)) AS INT) AS recency_days,
                   COUNT(DISTINCT v.order_id) AS frequency,
                   ROUND(SUM(v.monetary), 2) AS monetary
            FROM order_value v JOIN olist_customers c ON c.customer_id = v.customer_id
            GROUP BY c.customer_unique_id
        ),
        scored AS (
            SELECT *, NTILE(5) OVER (ORDER BY recency_days DESC) AS r_score,
                   NTILE(5) OVER (ORDER BY frequency) AS f_score,
                   NTILE(5) OVER (ORDER BY monetary) AS m_score
            FROM rfm
        )
        SELECT r_score, f_score, m_score, COUNT(*) AS users, ROUND(AVG(monetary), 2) AS avg_monetary
        FROM scored GROUP BY 1, 2, 3 ORDER BY 1 DESC, 2 DESC, 3 DESC
    """)


# ---------------- 5. 复购分析 ----------------

def get_repurchase_rate() -> str:
    """获取整体复购率（customer_unique_id 人级口径）。回答客户留存/复购问题时使用。"""
    return _run("""
        WITH cust_orders AS (
            SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS order_cnt
            FROM olist_orders o JOIN olist_customers c ON c.customer_id = o.customer_id
            WHERE o.order_status = 'delivered' GROUP BY 1
        )
        SELECT COUNT(*) AS total_customers,
               SUM(CASE WHEN order_cnt >= 2 THEN 1 ELSE 0 END) AS repeat_customers,
               ROUND(100.0 * SUM(CASE WHEN order_cnt >= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate_pct
        FROM cust_orders
    """)


# ---------------- 6. 地域分布 ----------------

def get_geo_sales() -> str:
    """获取各州 GMV 与占比（买家口径 Top10）。回答地域/市场分布问题时使用。"""
    return _run("""
        SELECT c.customer_state,
               COUNT(DISTINCT o.order_id) AS orders,
               ROUND(SUM(oi.price + oi.freight_value), 2) AS gmv,
               ROUND(100.0 * SUM(oi.price + oi.freight_value)
                   / SUM(SUM(oi.price + oi.freight_value)) OVER (), 2) AS gmv_share_pct
        FROM olist_orders o
        JOIN olist_order_items oi ON oi.order_id = o.order_id
        JOIN olist_customers c ON c.customer_id = o.customer_id
        WHERE o.order_status = 'delivered'
        GROUP BY 1 ORDER BY gmv DESC LIMIT 10
    """)


# ---------------- 7. 履约时效 ----------------

def get_delivery_performance() -> str:
    """获取履约时效总览（发货时长/配送时长/总时长/迟到率）。回答物流、交付体验问题时使用。"""
    return _run("""
        SELECT ROUND(AVG(julianday(order_delivered_carrier_date) - julianday(order_purchase_timestamp)), 2) AS avg_handover_days,
               ROUND(AVG(julianday(order_delivered_customer_date) - julianday(order_delivered_carrier_date)), 2) AS avg_shipping_days,
               ROUND(AVG(julianday(order_delivered_customer_date) - julianday(order_purchase_timestamp)), 2) AS avg_total_days,
               ROUND(100.0 * SUM(CASE WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 1 ELSE 0 END) / COUNT(*), 2) AS late_rate_pct
        FROM olist_orders
        WHERE order_status = 'delivered'
          AND order_delivered_carrier_date IS NOT NULL
          AND order_delivered_customer_date IS NOT NULL
    """)


# ---------------- 8. 口碑洞察 ----------------

def get_review_insights() -> str:
    """获取评分分布及各评分档的物流表现（评价去重口径：每单保留最新）。回答口碑/差评原因问题时使用。"""
    return _run("""
        WITH latest_review AS (
            SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.order_id ORDER BY r.review_answer_timestamp DESC) AS rn
            FROM olist_order_reviews r
        ), lr AS (SELECT order_id, review_score FROM latest_review WHERE rn = 1)
        SELECT lr.review_score,
               COUNT(*) AS orders,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS score_share_pct,
               ROUND(AVG(julianday(o.order_delivered_customer_date) - julianday(o.order_delivered_carrier_date)), 2) AS avg_shipping_days,
               ROUND(100.0 * SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END) / COUNT(*), 2) AS late_rate_pct
        FROM lr
        JOIN olist_orders o ON o.order_id = lr.order_id
        WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
          AND o.order_delivered_carrier_date IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)


# ---------------- 9. 增长拆解（P3 核心） ----------------

def get_growth_decomposition() -> str:
    """获取月度增长引擎拆解：GMV 环比增速 + 新客/存量 GMV 结构。回答'为什么增长/停滞'类问题时的第一步。"""
    conn = sqlite3.connect(DB)
    try:
        cur = conn.cursor()
        # 建临时表（TEMP TABLE 是连接级的，必须和查询同连接）
        cur.execute("DROP TABLE IF EXISTS tmp_first_order")
        cur.execute("""
            CREATE TEMP TABLE tmp_first_order AS
            SELECT c.customer_unique_id,
                   MIN(strftime('%Y-%m', o.order_purchase_timestamp)) AS cohort_month
            FROM olist_orders o JOIN olist_customers c ON c.customer_id = o.customer_id
            WHERE o.order_status = 'delivered' GROUP BY 1
        """)
        cur.execute("CREATE INDEX idx_tfo_uid ON tmp_first_order(customer_unique_id)")
        df = pd.read_sql_query("""
            WITH monthly AS (
                SELECT strftime('%Y-%m', o.order_purchase_timestamp) AS ym,
                       COUNT(DISTINCT o.order_id) AS orders,
                       ROUND(SUM(oi.price + oi.freight_value), 2) AS gmv,
                       ROUND(SUM(oi.price + oi.freight_value) / COUNT(DISTINCT o.order_id), 2) AS aov
                FROM olist_orders o JOIN olist_order_items oi ON oi.order_id = o.order_id
                WHERE o.order_status = 'delivered' AND o.order_purchase_timestamp >= '2017-01-01'
                GROUP BY 1
            ),
            trend AS (
                SELECT ym, orders, gmv, aov,
                       ROUND(100.0 * (gmv - LAG(gmv) OVER (ORDER BY ym)) / LAG(gmv) OVER (ORDER BY ym), 1) AS gmv_mom_pct
                FROM monthly
            ),
            engine AS (
                SELECT strftime('%Y-%m', o.order_purchase_timestamp) AS ym,
                       CASE WHEN fo.cohort_month = strftime('%Y-%m', o.order_purchase_timestamp)
                            THEN 'new' ELSE 'existing' END AS cust_type,
                       SUM(oi.price + oi.freight_value) AS gmv
                FROM olist_orders o
                JOIN olist_customers c ON c.customer_id = o.customer_id
                JOIN tmp_first_order fo ON fo.customer_unique_id = c.customer_unique_id
                JOIN olist_order_items oi ON oi.order_id = o.order_id
                WHERE o.order_status = 'delivered' AND o.order_purchase_timestamp >= '2017-01-01'
                GROUP BY 1, 2
            )
            SELECT t.ym, t.orders, t.gmv, t.gmv_mom_pct, t.aov,
                   ROUND(MAX(CASE WHEN e.cust_type = 'new' THEN e.gmv END), 2) AS gmv_new_cust,
                   ROUND(100.0 * MAX(CASE WHEN e.cust_type = 'new' THEN e.gmv END) / t.gmv, 1) AS new_cust_gmv_pct
            FROM trend t JOIN engine e ON e.ym = t.ym
            GROUP BY t.ym, t.orders, t.gmv, t.gmv_mom_pct, t.aov ORDER BY t.ym
        """, conn)
        return df.to_string(index=False)
    finally:
        conn.close()


# ---------------- 10. 假设验证（P3） ----------------

def get_new_customers_trend() -> str:
    """获取月度新客数（首单月口径的获客曲线）。验证'获客见顶'假设、回答拉新问题时使用。"""
    conn = sqlite3.connect(DB)
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS tmp_first_order")
        cur.execute("""
            CREATE TEMP TABLE tmp_first_order AS
            SELECT c.customer_unique_id,
                   MIN(strftime('%Y-%m', o.order_purchase_timestamp)) AS cohort_month
            FROM olist_orders o JOIN olist_customers c ON c.customer_id = o.customer_id
            WHERE o.order_status = 'delivered' GROUP BY 1
        """)
        cur.execute("CREATE INDEX idx_tfo_uid ON tmp_first_order(customer_unique_id)")
        df = pd.read_sql_query("""
            SELECT cohort_month, COUNT(*) AS new_customers,
                   SUM(COUNT(*)) OVER (ORDER BY cohort_month) AS cum_customers
            FROM tmp_first_order
            WHERE cohort_month >= '2017-01'
            GROUP BY 1 ORDER BY 1
        """, conn)
        return df.to_string(index=False)
    finally:
        conn.close()


def get_experience_trend() -> str:
    """获取 2017 vs 2018 体验指标对比（履约时长/迟到率/平均评分）。验证'体验恶化'假设时使用。"""
    return _run("""
        SELECT strftime('%Y', o.order_purchase_timestamp) AS yr,
               ROUND(AVG(julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp)), 2) AS avg_total_days,
               ROUND(100.0 * SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END) / COUNT(*), 2) AS late_rate_pct,
               ROUND(AVG(r.review_score), 2) AS avg_review_score
        FROM olist_orders o
        JOIN (SELECT order_id, review_score,
                     ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY review_answer_timestamp DESC) AS rn
              FROM olist_order_reviews) r ON r.order_id = o.order_id AND r.rn = 1
        WHERE o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL
          AND o.order_purchase_timestamp >= '2017-01-01'
        GROUP BY 1 ORDER BY 1
    """)


# ---------------- 工具注册表（LLM 可见） ----------------

TOOL_FUNCS = {
    "get_monthly_gmv": get_monthly_gmv,
    "get_order_status": get_order_status,
    "get_product_abc": get_product_abc,
    "get_rfm_summary": get_rfm_summary,
    "get_repurchase_rate": get_repurchase_rate,
    "get_geo_sales": get_geo_sales,
    "get_delivery_performance": get_delivery_performance,
    "get_review_insights": get_review_insights,
    "get_growth_decomposition": get_growth_decomposition,
    "get_new_customers_trend": get_new_customers_trend,
    "get_experience_trend": get_experience_trend,
}


def _params(props: dict, required: list) -> dict:
    return {"type": "object", "properties": props, "required": required}


TOOL_SPECS = [
    {"type": "function", "function": {"name": "get_monthly_gmv",
        "description": "月度 GMV、订单量、客单价趋势（delivered 口径，2017-01 起）。回答增长/趋势/波动类问题必查。",
        "parameters": _params({"start": {"type": "string", "description": "起始月 YYYY-MM，默认 2017-01"},
                               "end": {"type": "string", "description": "结束月 YYYY-MM，默认 2018-08"}}, [])}},
    {"type": "function", "function": {"name": "get_order_status",
        "description": "订单状态分布与占比。回答履约健康、取消率类问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_product_abc",
        "description": "品类 ABC 分析：收入 Top15 + 累计占比 + 分级。回答品类结构/头部集中度问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_rfm_summary",
        "description": "RFM 客户分层汇总（参照日 2018-10-17）。回答客户价值/分层问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_repurchase_rate",
        "description": "整体复购率（人级口径）。回答客户留存/复购问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_geo_sales",
        "description": "各州 GMV 与占比 Top10（买家口径）。回答地域/市场分布问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_delivery_performance",
        "description": "履约时效总览：发货/配送/总时长 + 迟到率。回答物流与交付体验问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_review_insights",
        "description": "评分分布 × 各评分档物流表现（评价每单取最新）。回答口碑/差评原因问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_growth_decomposition",
        "description": "月度增长引擎拆解：GMV 环比 + 新客/存量 GMV 结构占比。回答'为什么增长/停滞'类问题的第一步。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_new_customers_trend",
        "description": "月度新客数与累计获客曲线（首单月口径）。验证获客见顶假设、回答拉新问题时使用。", "parameters": _params({}, [])}},
    {"type": "function", "function": {"name": "get_experience_trend",
        "description": "2017 vs 2018 体验指标对比：履约时长/迟到率/平均评分。验证'体验恶化'假设时使用。", "parameters": _params({}, [])}},
]


def dispatch(name: str, args: dict) -> str:
    """按名称调度工具，返回文本结果。异常时返回错误说明（不中断 Agent 循环）。"""
    func = TOOL_FUNCS.get(name)
    if func is None:
        return f"未知工具: {name}"
    try:
        return func(**args)
    except Exception as e:
        return f"工具执行出错: {e}"
