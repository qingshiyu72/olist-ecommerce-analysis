# -*- coding: utf-8 -*-
"""
P4: LLM 评论情感分析 + 幻觉验证
用法: python sentiment_analysis.py
- 从 .api_key 读 DeepSeek 密钥（绝不写进代码/报告）
- 抽样 1000 条葡语评论（评分 1~5 每档 200，分层抽样）
- 20 条/批调 API，三分类 + 负面归因
- 幻觉验证：LLM 情感 vs 用户真实打分的一致率
"""
import os
import json
import time
import sqlite3
import pandas as pd
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "olist.db")
KEY_FILE = os.path.join(BASE, ".api_key")
OUT = os.path.join(BASE, "output")
SAMPLE_PER_SCORE = 200      # 每档抽样，共 1000 条
BATCH = 20                  # 每批评论数
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """你是电商评论分析助手。用户会给出若干条巴西电商的葡语评论（每行格式：编号: 评论内容）。
请对每条评论独立判断：
- sentiment: positive / negative / neutral
- category: 仅当 sentiment=negative 时给出主因，取值:
  logistics_delay(物流慢或送达问题) / product_quality(商品质量) / seller_issue(发货或卖家服务) / other
  非负面时 category 固定为 "none"
严格输出 JSON 对象: {"results": [{"id": <编号>, "sentiment": "...", "category": "..."}]}
不要输出任何其他文字。"""


def load_key():
    with open(KEY_FILE, encoding="utf-8") as f:
        return f.read().strip()


def sample_reviews():
    """去重（每单最新评价）+ 分层抽样"""
    conn = sqlite3.connect(DB)
    q = """
    WITH lr AS (
      SELECT order_id, review_score, review_comment_message,
             ROW_NUMBER() OVER (PARTITION BY order_id
                 ORDER BY review_answer_timestamp DESC) AS rn
      FROM olist_order_reviews
      WHERE review_comment_message IS NOT NULL
        AND TRIM(review_comment_message) != ''
    )
    SELECT order_id, review_score, review_comment_message FROM lr WHERE rn = 1
    """
    df = pd.read_sql_query(q, conn)
    conn.close()
    sampled = pd.concat(
        [g.sample(min(SAMPLE_PER_SCORE, len(g)), random_state=42)
         for _, g in df.groupby("review_score")]
    ).reset_index(drop=True).reset_index().rename(columns={"index": "id"})
    return sampled


def call_api(key, batch):
    lines = "\n".join(
        f"{r.id}: {r.review_comment_message[:500]}" for r in batch.itertuples()
    )
    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": lines},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)["results"]


def main():
    key = load_key()
    sampled = sample_reviews()
    print(f"抽样完成: {len(sampled)} 条 (评分 1~5 每档 {SAMPLE_PER_SCORE})")

    results = []
    batches = [sampled.iloc[i:i + BATCH] for i in range(0, len(sampled), BATCH)]
    out_csv = os.path.join(OUT, "llm_sentiment_results.csv")
    t0 = time.time()
    for bi, batch in enumerate(batches, 1):
        res = None
        for attempt in range(3):
            try:
                res = call_api(key, batch)
                break
            except Exception as e:
                print(f"  批{bi} 第{attempt + 1}次失败: {e}")
                time.sleep(3)
        if res is None:
            print(f"  批{bi} 放弃，跳过")
            continue
        results.extend(res)
        pd.DataFrame(results).to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"批 {bi}/{len(batches)} 完成，累计 {len(results)} 条 ({time.time() - t0:.0f}s)")
        time.sleep(0.4)

    # ---------- 幻觉验证：LLM 情感 vs 用户真实打分 ----------
    rdf = pd.DataFrame(results)
    rdf["id"] = pd.to_numeric(rdf["id"], errors="coerce").astype("Int64")
    rdf["sentiment"] = rdf["sentiment"].astype(str).str.lower().str.strip()
    df = sampled.merge(rdf, on="id", how="inner")
    df["expected"] = df["review_score"].apply(
        lambda s: "negative" if s <= 2 else ("positive" if s >= 4 else "neutral")
    )
    df["match"] = df["sentiment"] == df["expected"]

    print("\n===== 幻觉验证：LLM 情感 vs 用户打分一致率 =====")
    print(f"总体一致率: {df['match'].mean() * 100:.1f}%  (n={len(df)})")
    print("分评分档一致率(%):")
    print(df.groupby("review_score")["match"].mean().mul(100).round(1))

    neg = df[df["sentiment"] == "negative"]
    if len(neg):
        print("\n===== 负面评论归因分布 =====")
        print(neg["category"].value_counts())

    out_full = os.path.join(OUT, "llm_sentiment_validated.csv")
    df.to_csv(out_full, index=False, encoding="utf-8-sig")
    print(f"\n完成: {out_csv}\n      {out_full}")


if __name__ == "__main__":
    main()
