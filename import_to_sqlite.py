# -*- coding: utf-8 -*-
"""
Olist 数据集 → SQLite 入库脚本（P1）
用法: python import_to_sqlite.py
产出: olist-analysis/olist.db （9 张表，表名去掉 _dataset 后缀）
"""
import os
import sqlite3
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
DB_PATH = os.path.join(BASE, "olist.db")

TABLES = [
    "olist_customers_dataset",
    "olist_geolocation_dataset",
    "olist_order_items_dataset",
    "olist_order_payments_dataset",
    "olist_order_reviews_dataset",
    "olist_orders_dataset",
    "olist_products_dataset",
    "olist_sellers_dataset",
    "product_category_name_translation",
]

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("已删除旧库，重新导入")
    conn = sqlite3.connect(DB_PATH)
    for t in TABLES:
        csv_path = os.path.join(DATA, t + ".csv")
        df = pd.read_csv(csv_path)
        name = t.replace("_dataset", "")
        df.to_sql(name, conn, if_exists="replace", index=False)
        print(f"导入 {name:30s} {len(df):>8} 行 x {df.shape[1]} 列")
    conn.commit()

    print("\n=== 快速质检 ===")
    cur = conn.cursor()
    # 1) 订单主键唯一性
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT order_id) FROM olist_orders")
    total, distinct = cur.fetchone()
    print(f"orders: {total} 行, 唯一 order_id {distinct} -> {'OK' if total == distinct else 'DUPLICATE!'}")
    # 2) reviews 重复 review_id（已知坑）
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT review_id), COUNT(DISTINCT order_id) FROM olist_order_reviews")
    total, distinct_rid, distinct_oid = cur.fetchone()
    print(f"reviews: {total} 行, 唯一 review_id {distinct_rid} (重复 {total - distinct_rid}), 唯一 order_id {distinct_oid}")
    # 3) 时间范围
    cur.execute("SELECT MIN(order_purchase_timestamp), MAX(order_purchase_timestamp) FROM olist_orders")
    tmin, tmax = cur.fetchone()
    print(f"下单时间范围: {tmin} ~ {tmax}")
    # 4) 订单状态分布
    cur.execute("SELECT order_status, COUNT(*) FROM olist_orders GROUP BY order_status ORDER BY 2 DESC")
    print("订单状态分布:", cur.fetchall())
    # 5) geolocation 重复 zip 前缀（已知坑）
    cur.execute("SELECT COUNT(*), COUNT(DISTINCT geolocation_zip_code_prefix) FROM olist_geolocation")
    total, distinct_zip = cur.fetchone()
    print(f"geolocation: {total} 行, 唯一 zip 前缀 {distinct_zip} (平均每前缀 {total/distinct_zip:.1f} 行)")
    conn.close()
    print(f"\n完成: {DB_PATH}")

if __name__ == "__main__":
    main()
