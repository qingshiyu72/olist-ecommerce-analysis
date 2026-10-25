"""配送时效对评价分数的显著性检验

把「迟到单 1 星率 37.9%」这类描述性对比，升级为统计推断：
分布检验 + 效应量 + 置信区间 + 剂量反应 + 分层稳健性 + 实验样本量估算。

口径说明：
- 只取 order_status=delivered 且送达日期、预计送达日期、评价分数均非空的订单
- 一单多评取最新一条（review_creation_date 最大）
- 迟到 = 实际送达日期 > 预计送达日期（按天计算，>0 即迟到）

用法：python delivery_significance_test.py
"""
import numpy as np
import pandas as pd
from scipy import stats

DATA = "data"


def load():
    orders = pd.read_csv(DATA + "/olist_orders_dataset.csv")
    reviews = pd.read_csv(DATA + "/olist_order_reviews_dataset.csv")
    customers = pd.read_csv(DATA + "/olist_customers_dataset.csv")

    # 一单多评 → 保留最新一条
    reviews = reviews.sort_values("review_creation_date").drop_duplicates("order_id", keep="last")

    df = orders.merge(reviews[["order_id", "review_score"]], on="order_id", how="inner")
    df = df.merge(customers[["customer_id", "customer_state"]], on="customer_id", how="left")
    df = df[df["order_status"] == "delivered"].dropna(
        subset=["order_delivered_customer_date", "order_estimated_delivery_date", "review_score"]
    )
    for col in ["order_delivered_customer_date", "order_estimated_delivery_date"]:
        df[col] = pd.to_datetime(df[col])

    df["delay_days"] = (
        df["order_delivered_customer_date"] - df["order_estimated_delivery_date"]
    ).dt.total_seconds() / 86400
    df["is_late"] = df["delay_days"] > 0
    return df


def main():
    df = load()
    late = df.loc[df["is_late"], "review_score"]
    ontime = df.loc[~df["is_late"], "review_score"]

    print("=" * 60)
    print("1. 样本与分组")
    print("=" * 60)
    print(f"参与分析订单 {len(df):,}  迟到 {len(late):,} ({len(late)/len(df)*100:.1f}%)")
    for name, s in [("迟到", late), ("准时/提前", ontime)]:
        print(f"  {name:<8} 均值={s.mean():.3f}  中位数={s.median():.0f} "
              f"标准差={s.std():.3f}  差评率(≤2星)={(s <= 2).mean()*100:.1f}%")

    print()
    print("=" * 60)
    print("2. 分布检验（评分 1-5 为有序变量，用秩检验而非 t 检验）")
    print("=" * 60)
    u, p = stats.mannwhitneyu(late, ontime, alternative="two-sided")
    n1, n2 = len(late), len(ontime)
    cliff = 2 * u / (n1 * n2) - 1
    print(f"Mann-Whitney U = {u:,.1f},  p = {p:.3e}")
    print(f"Cliff's delta  = {cliff:.4f}（|δ|>0.474 为大效应，负值=迟到组更低）")

    diff = late.mean() - ontime.mean()
    rng = np.random.default_rng(42)
    boots = [rng.choice(late.values, n1).mean() - rng.choice(ontime.values, n2).mean()
             for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    print(f"均值差 = {diff:.3f} 分，bootstrap 95%CI [{lo:.3f}, {hi:.3f}]")

    print()
    print("=" * 60)
    print("3. 剂量反应：延迟越久，评分越低？")
    print("=" * 60)
    bins = [-np.inf, 0, 3, 7, 15, 30, np.inf]
    labels = ["提前/准时", "1-3天", "4-7天", "8-15天", "16-30天", ">30天"]
    df["delay_bin"] = pd.cut(df["delay_days"], bins=bins, labels=labels)
    g = df.groupby("delay_bin", observed=True)["review_score"].agg(["count", "mean", "median"])
    g["差评率%"] = df.groupby("delay_bin", observed=True)["review_score"].apply(
        lambda s: (s <= 2).mean() * 100)
    print(g.round(3).to_string())
    rho, p_rho = stats.spearmanr(df["delay_days"], df["review_score"])
    print(f"\nSpearman 秩相关 rho = {rho:.4f}, p = {p_rho:.3e}")

    print()
    print("=" * 60)
    print("4. 稳健性：按客户所在州分层，效应是否一致")
    print("=" * 60)
    rows = []
    for state, sub in df.groupby("customer_state"):
        a = sub.loc[sub["is_late"], "review_score"]
        b = sub.loc[~sub["is_late"], "review_score"]
        if len(sub) < 300 or len(a) < 30:
            continue
        rows.append((state, len(sub), len(a), b.mean(), a.mean(), a.mean() - b.mean()))
    rows.sort(key=lambda x: -x[1])
    print(f"{'州':<5}{'样本':>7}{'迟到数':>7}{'准时均分':>10}{'迟到均分':>10}{'均分差':>9}")
    for r in rows[:8]:
        print(f"{r[0]:<5}{r[1]:>7,}{r[2]:>7,}{r[3]:>10.3f}{r[4]:>10.3f}{r[5]:>9.3f}")
    negatives = sum(1 for r in rows if r[5] < 0)
    print(f"\n{len(rows)} 个州中 {negatives} 个州均分差为负；"
          f"范围 {min(r[5] for r in rows):.2f} ~ {max(r[5] for r in rows):.2f}")

    state_tbl = df.groupby("customer_state").agg(
        n=("order_id", "size"), late_rate=("is_late", "mean"), avg_score=("review_score", "mean"))
    state_tbl = state_tbl[state_tbl["n"] > 300]
    c = stats.spearmanr(state_tbl["late_rate"], state_tbl["avg_score"])
    print(f"州级：准时率 vs 平均分  rho = {c.statistic:.4f}, p = {c.pvalue:.4f}")

    print()
    print("=" * 60)
    print("5. 实验样本量估算（α=0.05, 功效=0.80）")
    print("=" * 60)
    z_a, z_b = 1.96, 0.8416
    sd = ontime.std()
    for delta in (0.10, 0.20, 0.30):
        n = 2 * (z_a + z_b) ** 2 * sd ** 2 / delta ** 2
        print(f"  检出 {delta:.2f} 分差异 → 每组 {int(np.ceil(n)):,} 单（σ={sd:.2f}）")
    p1, p2 = 0.92, 0.97
    n_prop = (z_a + z_b) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / (p2 - p1) ** 2
    print(f"  承诺达成率 92%→97% → 每组 {int(np.ceil(n_prop)):,} 单")

    print()
    print("提示：以上均为观察性关联，不能直接解释为因果。见 docs/P5_配送时效与评分的显著性检验.md")


if __name__ == "__main__":
    main()
