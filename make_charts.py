# -*- coding: utf-8 -*-
"""
P5: 生成项目核心图表（6 张，存 output/charts/）
用法: python make_charts.py
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]   # Windows 中文字体
plt.rcParams["axes.unicode_minus"] = False

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "output")
CH = os.path.join(OUT, "charts")
os.makedirs(CH, exist_ok=True)

BLUE, RED, ORANGE, GRAY = "#378ADD", "#E24B4A", "#EF9F27", "#888780"


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(CH, name), dpi=150)
    plt.close(fig)
    print("生成", name)


# ---- 图1：月度 GMV 趋势（标注黑五与平台期）----
df = pd.read_csv(os.path.join(OUT, "09_growth_decomposition_4.csv"))
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(df["ym"], df["gmv"] / 10000, marker="o", ms=3, color=BLUE, lw=1.5)
peak = df.loc[df["gmv"].idxmax()]
ax.annotate(f"2017-11 黑五峰值\n{peak['gmv']/10000:.0f} 万",
            xy=(peak["ym"], peak["gmv"] / 10000),
            xytext=(6, 10), textcoords="offset points",
            fontsize=10, color=RED, ha="left")
ax.axvspan(5.5, 19.5, color=ORANGE, alpha=0.10)
ax.text(12, df["gmv"].min() / 10000 * 0.98, "2018 年：增长停滞平台期（约 100 万/月）",
        fontsize=10, color="#854F0B", ha="center")
ax.set_title("月度 GMV 趋势（delivered 口径，2017-01 起）", fontsize=13)
ax.set_ylabel("GMV（万元）")
ax.set_xticks(range(0, len(df), 3))
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
ax.grid(axis="y", alpha=0.3)
save(fig, "01_gmv_trend.png")

# ---- 图2：月度新客曲线（获客见顶）----
d11 = pd.read_csv(os.path.join(OUT, "11_hypothesis_verification_5.csv"))
fig, ax = plt.subplots(figsize=(10, 4.5))
colors = [RED if ym >= "2018-02" else BLUE for ym in d11["cohort_month"]]
ax.bar(d11["cohort_month"], d11["new_customers"], color=colors, alpha=0.85)
peak_idx = d11["new_customers"].idxmax()
ax.annotate("2018-01 新客见顶 6,842\n此后回落至 ~6,100（-10%）",
            xy=(peak_idx, d11["new_customers"].max()),
            xytext=(peak_idx + 1.5, d11["new_customers"].max() * 0.95),
            fontsize=10, color=RED,
            arrowprops=dict(arrowstyle="->", color=RED))
ax.set_title("月度新客数（首单月口径）—— 增长引擎失速的直接证据", fontsize=13)
ax.set_ylabel("新客数")
ax.set_xticks(range(0, len(d11), 3))
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
ax.grid(axis="y", alpha=0.3)
save(fig, "02_new_customers.png")

# ---- 图3：收入结构 —— 新客依赖度 ----
fig, ax = plt.subplots(figsize=(10, 4.2))
ax.plot(df["ym"], df["new_cust_gmv_pct"], marker="o", ms=3, color=BLUE, lw=1.5)
ax.axhline(97, color=RED, ls="--", lw=1)
ax.text(0.3, 97.05, "97% 警戒线：收入几乎全靠新客首购（复购率仅 3%）", fontsize=10, color=RED)
ax.set_ylim(94, 100)
ax.set_title("新客 GMV 占比 —— 单一收入结构是增长停滞的放大器", fontsize=13)
ax.set_ylabel("新客 GMV 占比（%）")
ax.set_xticks(range(0, len(df), 3))
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
ax.grid(axis="y", alpha=0.3)
save(fig, "03_revenue_structure.png")

# ---- 图4：评分档 vs 物流表现（口碑 × 履约）----
d08 = pd.read_csv(os.path.join(OUT, "08_review_insights_1.csv"))
fig, ax = plt.subplots(figsize=(8, 4.2))
bars = ax.bar(d08["review_score"].astype(str) + "星", d08["late_rate_pct"],
              color=[RED, "#F0997B", GRAY, "#85B7EB", BLUE])
for b, v in zip(bars, d08["late_rate_pct"]):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.5, f"{v:.1f}%", ha="center", fontsize=10)
ax.set_title("各评分档的迟到率 —— 低分与\"超承诺送达\"强相关", fontsize=13)
ax.set_ylabel("迟到率（%）")
ax.grid(axis="y", alpha=0.3)
save(fig, "04_late_by_score.png")

# ---- 图5：LLM 情感 vs 用户打分一致率（幻觉验证）----
d4 = pd.read_csv(os.path.join(OUT, "llm_sentiment_validated.csv"))
acc = d4.groupby("review_score")["match"].mean().mul(100)
fig, ax = plt.subplots(figsize=(8, 4.2))
cols = [RED if v < 50 else BLUE for v in acc.values]
bars = ax.bar(acc.index.astype(str) + "星", acc.values, color=cols)
for b, v in zip(bars, acc.values):
    ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}%", ha="center", fontsize=10)
ax.axhline(70.9, color=GRAY, ls="--", lw=1)
ax.text(4.1, 72, f"总体 70.9%", fontsize=10, color=GRAY)
ax.set_ylim(0, 105)
ax.set_title("LLM 情感判断 vs 用户真实打分一致率 —— 极端可靠、中间模糊", fontsize=13)
ax.set_ylabel("一致率（%）")
ax.grid(axis="y", alpha=0.3)
save(fig, "05_llm_accuracy.png")

# ---- 图6：负面评论归因分布 ----
neg = d4[d4["sentiment"] == "negative"]["category"].value_counts()
label_map = {"logistics_delay": "物流延误", "product_quality": "商品质量",
             "seller_issue": "卖家/发货服务", "other": "其他"}
labels = [label_map.get(k, k) for k in neg.index]
fig, ax = plt.subplots(figsize=(8, 4.2))
bars = ax.barh(labels[::-1], neg.values[::-1], color=[GRAY, ORANGE, "#F0997B", RED][::-1][:len(neg)])
for b, v in zip(bars, neg.values[::-1]):
    ax.text(v + 2, b.get_y() + b.get_height() / 2, f"{v} ({v/neg.sum()*100:.0f}%)",
            va="center", fontsize=10)
ax.set_title(f"LLM 负面评论归因分布（n={neg.sum()}）—— 物流是差评第一大主因", fontsize=13)
ax.set_xlabel("评论条数")
ax.grid(axis="x", alpha=0.3)
save(fig, "06_negative_reasons.png")

print("\n全部图表完成 →", CH)
