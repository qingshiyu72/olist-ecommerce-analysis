# Olist 电商经营分析 + LLM 评论洞察

> 基于 10 万条巴西电商真实订单的经营分析项目：SQL 指标体系 → 增长归因 → LLM 评论挖掘 → 幻觉验证。
> 一个人 + AI 协作完成，全程 0 服务器成本。

## 核心结论 Top 5

1. **2018 年 GMV 停滞的根因是获客引擎失速**：月新客数 2018-01 见顶（6,842）后回落 10%，而平台 97% 的收入依赖新客首购、复购率仅 3.0% —— 已用排除法排除品类结构与体验恶化
2. **物流是差评第一大主因（35.8%）**：LLM 分析 1,000 条葡语评论 + 统计证据（1 星订单迟到率 37.9%）三角验证闭环
3. **隐性风险**：迟到率 6.5% → 9.3%（2017→2018），履约在变快但承诺在变激进——口碑的慢性毒药
4. **LLM 能力边界地图**：情感判断"极端可靠、中间模糊"（1/5 星一致率 93%+，3 星仅 12%）→ 落地方案：置信度路由
5. **数据陷阱实战**：评价重复（814 条）、地理表冗余（52.6 行/前缀）、采集截尾误判为业务崩盘——先质检后分析

## 架构

```
9 张 CSV ──► SQLite 数仓（质检先行）
              │
              ├── SQL 指标层：11 个模块（GMV/RFM/复购/履约/口碑/归因）
              │        └─ 窗口函数 · CTE · TEMP TABLE 查询优化
              │
              ├── LLM 分析层：分层抽样 → 批量 API → 结构化输出
              │        └─ 幻觉验证：LLM 情感 × 用户真实评分交叉对比
              │
              └── 报告层：归因故事 + 业务建议 + 6 张图表
```

## 仓库结构

```
├── data/                  # 原始数据（9 张 CSV）
├── sql/                   # 01~11 分析模块（每个含口径说明与考点注释）
├── docs/                  # 报告：质检 / 归因 / LLM / 判断清单
├── output/                # SQL 结果 CSV + charts/ 图表
├── import_to_sqlite.py    # 入库 + 质检
├── run_sql.py             # SQL 运行器（跑模块 + 导出 CSV）
├── sentiment_analysis.py  # LLM 情感分析 + 幻觉验证
└── make_charts.py         # 图表生成
```

## 复现

```bash
pip install pandas requests matplotlib
python import_to_sqlite.py      # 建库 + 质检
python run_sql.py               # 全部分析模块
echo <your-deepseek-key> > .api_key   # P4 需要自备 key
python sentiment_analysis.py
python make_charts.py
```

## 技术栈

SQLite · SQL（窗口函数 / CTE / 索引优化）· Python（pandas / requests / matplotlib）· DeepSeek API · Prompt 工程 · 统计验证

## 报告

详见 [docs/Olist经营分析报告.md](docs/Olist经营分析报告.md) ｜ [docs/P3_归因分析报告.md](docs/P3_归因分析报告.md) ｜ [docs/P4_LLM情感分析报告.md](docs/P4_LLM情感分析报告.md)
