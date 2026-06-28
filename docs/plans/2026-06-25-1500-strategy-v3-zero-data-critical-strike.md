# OKX-Bot Strategy V3.1 — Zero-Data-Cost 暴击流组合（扩频版）

> 目标：$7 → $50 · 设计时间：2026-06-25 15:00 · 版本：V3.0 → V3.1 · 设计人：量化研究员 / 算法工程师 / crypto 交易员三栈视角
>
> 本文件是 V1（已废止）与 V2（被 `PHASE_0_REPORT.md` 与 `okx-algo.md` 联合证伪）的**结构性替代方案**，对应 V2 §3 Option B 主线 + 多 edge 并行扩展。
>
> Status：approved-for-gated-live（2026-06-25 21:28 二审通过；允许进入 research/backtest，且仅在 §18 全部闸门 PASS 后启动实盘）

> **本文档已拆分为三份独立文件，按 `docs/` 职责分离：**
> - **本文档（执行计划）** — 推进路线、验收闸门、失败处理、审计决策签收
> - **Edge 信号设计** → [`docs/design/2026-06-27-strategy-v3-edge-design.md`](../design/2026-06-27-strategy-v3-edge-design.md)（信号定义、阈值、验证规则、文献依据）
> - **共享执行架构** → [`docs/architecture/2026-06-27-strategy-v3-execution-architecture.md`](../architecture/2026-06-27-strategy-v3-execution-architecture.md)（模块边界、数据流、Strategy Protocol、状态机、熔断、持久化）
> - **漂移分析需求** → [`docs/requirements/2026-06-27-live-echo-drift-requirements.md`](../requirements/2026-06-27-live-echo-drift-requirements.md)
> - **漂移分析报告** → [`docs/reports/2026-06-27-live-echo-drift-analysis-report.md`](../reports/2026-06-27-live-echo-drift-analysis-report.md)
> - 任何 edge 参数修改请直接更新设计文档而非本文档。执行架构变更请更新架构文档。本文档仅跟踪推进、闸门与审计状态。

***

## 0. TL;DR

**V3.1 = 7 条 zero-data-cost edge 的暴击流组合 + 共享暴击流仓位状态机 + 复用现有 backtest 骨架。**

- V1 已死：200-400ms 延迟 vs HFT 同向追清算 = 物理上输。
- V2 主策略已死：清算流真实数据在 2026 全员 paywall，$7 本金 × $30/月数据费 = 长期 EV 永负。
- V3.1 撤掉对清算流的依赖，在 zero-data-cost 范围内组合 **7** 条散户行为型 edge，用暴击流仓位规则去吃右尾路径。
- 7 条 edge = **A** 上市 fade + **B** funding 极值反转 + **C** BTC-Alt β decoupling + **D** 周末 wick fade + **E** pre-funding settlement unwind + **K** 同主题 alt pair MR + **H** OI velocity + 价格滞涨。
- 主目标：$7 → $50；副目标：7 条 edge 的横向 Phase 0 回测报告 + 可复用 Paper→Live 框架。
- 数学诚实：daily edge ≈ 33% 不可能稳定复利，只在右尾路径上成立（概率估 25-75%）。"$50 是娱乐，框架是资产"。

***

## 1. 决策背景：从废墟里凝结出来的硬约束

### 1.1 V1/V2 死因复盘

| 方案 | 核心思路 | 死因 | 不可逆程度 |
|------|----------|------|-----------|
| V1：微观结构动量点火 | 追清算级联早期入场 | 200-400ms 延迟下与 HFT 同向竞速，本地代理永远是最后一棒 | 物理不可逆 |
| V2 主：清算尾声 fade | 让清算冲完做对手盘 | 真实清算 tick 流 2026 全员 paywall；OI 5min diff 代理回测胜率 10.99% / EV -0.41R | 数据基建不可逆 |
| V2 辅：新合约 fade | 上市后 pump-then-fade | 写了雏形但未回测验证 | 这是 V3 的入口 |

### 1.2 三维硬约束（违反任何一维即作废）

| 维度 | 数值 | 含义 |
|------|------|------|
| 资金 | **$7** | 任何 ≥ $5/月固定订阅都让 EV 长期为负 |
| 数据预算 | **$0/月** | Coinglass / Tardis 全部出局；只能用 OKX + Binance 免费公共 API |
| 网络延迟 | **200-400ms** | 信号尺度 ≥ 1 分钟才能容忍；sub-second 类策略物理出局 |

### 1.3 暴击流真实含义校准

暴击流在此处的可用版本是：**重仓 + 单笔 R 严格定死 + 命中不眷恋 + 不犹豫止损 + 不补仓 + 命中后强制提现到生存池**。这与 prop firm 评估场景（consistency rule / daily DD 限制）无关——这是私人资金，没有 platform-level consistency rule。详见架构文档 §6。

### 1.4 心理预期校准（数学版）

daily edge ≈ 33%/day 不可能稳定复利。本设计的 EV 数学是：单 edge 单笔 EV +0.3R~+0.5R，暴击流仓位放大到 +30%~+50% equity 变动，7 天内只需要 5-8 次净胜就达 $50。路径概率 25-75%（V3.1 频次拉上来后的保守估计）。

***

## 2. Edge 蓝图（概要 → 详见设计文档）

7 条 edge 的详细信号定义、阈值、准入准则、验证规则已全部迁移至独立设计文档：
→ **[`docs/design/2026-06-27-strategy-v3-edge-design.md`](../design/2026-06-27-strategy-v3-edge-design.md)**

### 设计文档包含以下内容

- Edge 准入准则（6 条：散户行为根源、数据零成本、延迟容忍 ≥ 1 分钟、OKX 永续可执行、频次匹配、证据闸门）
- 7 条 edge 的完整信号定义与阈值表格（A/B/C/D/E/K/H，含 A1/A2 子入场模式）
- Pair MR 的 cointegration 准入检验（ADF / Engle-Granger / half-life）
- H 的两阶段状态机（pre-burst 监测 + fade entry）
- 辅助信号 L（Long/Short Ratio）与 backlog G 的定义
- Ensemble 冲突消解规则（priority 排序、去重、互斥）
- 单 Edge 验收闸门表（样本数、胜率、EV(R)、PF、最大连亏、频次）
- 实盘运行中监控触发条件
- 滑点与交易成本建模参数
- 文献与经验依据（含 arxiv 2602.00776、Yellow.com、ScienceDirect 等）

### 横向参数简表（仅频率与 α 阶段 1R，供执行参考）

| ID | 名称 | 类型 | 频率假设 | 杠杆上限 | α 阶段 1R |
|----|------|------|----------|----------|-----------|
| A | 新合约上市 Fade | 事件型 | ≥ 2 笔/周 | 5-10x | 30% |
| B | Funding Rate 极值反转 | MR | ≥ 1 笔/天 | 6-8x | 20% |
| C | BTC-Alt β Decoupling | MR | ≥ 1 笔/天 | 8-10x | 20% |
| D | 周末低流动性 Wick Fade | 事件型 | ≥ 4 笔/周 | 5-7x | 15% |
| E | Pre-funding Settlement Unwind | MR | ≥ 5 笔/天 | 6-8x | 18% |
| K | 同主题 Alt Pair MR | MR | ≥ 3 笔/天 | 8-10x | 15% |
| H | OI Velocity + 价格滞涨 | MR | ≥ 3 笔/天 | 8-10x | 18% |

> 以上频率假设是研究假设，必须在 §18.4 横向回测实证确认后方可进入 live。

***

## 3. Strategy A~H 实现详情 → 详见设计文档

策略 A（上市 Fade）、B（Funding 极值反转）、C（β Decoupling）、D（周末 Wick）、E（Pre-funding Unwind）、K（Pair MR）、H（OI Velocity）的完整信号定义、触发条件、入场/出场规则、仓位 R 值、验收门槛详见设计文档：
→ [`docs/design/2026-06-27-strategy-v3-edge-design.md`](../design/2026-06-27-strategy-v3-edge-design.md) §5.1-§5.7

***

## 4. 暴击流仓位状态机与工程架构 → 详见架构文档

共享仓位状态机与工程架构已全部迁移至独立架构文档：
→ **[`docs/architecture/2026-06-27-strategy-v3-execution-architecture.md`](../architecture/2026-06-27-strategy-v3-execution-architecture.md)**

### 架构文档包含以下内容

- **暴击流仓位状态机**：4 阶段递进模型（α/β/γ/δ）、状态转换、退场与冷却规则、仓位计算公式、阶段切换条件
- **模块边界**：Edge / 仲裁 / 运行 / 状态 / 熔断 / 管道 / 集成七层职责，以及文件边界规则（不可违反）
- **Strategy Protocol**：统一 `compute_signals()` 接口、`StrategyConfig` 冻结数据类、edge 注册表
- **数据流**：回测数据流、实盘数据流、信号输出格式、管道输出格式
- **RiskGuard 全局熔断**：日最大回撤、连续亏损熔断、日交易上限
- **Ensemble 仲裁层**：priority 表、信号质量评分公式
- **持久化与日志**：交易流水 CSV、运行状态快照 JSON、缓存数据持久化规范
- **OKX API 集成**：订单执行参数、数据源契约、lookahead bias 防护

### 阶段与启用 strategy（供执行参考）

| 阶段 | 权益区间 | 单笔 1R | 杠杆上限 | 启用 strategy |
|------|----------|---------|----------|---------------|
| α 破壁 | $7-$14 | 18-30%（A 30%） | 10x | A + E |
| β 翻倍 | $14-$25 | 15-20% | 10x | A + B + E + H |
| γ 复利 | $25-$50 | 15-20% | 8x | A + B + C + E + K + H |
| δ 提现 | ≥ $50 | 10% | 5x | 全部 |

> 每条 edge 在 α/β 阶段的具体 1R 值由各 edge 设计文档定义，架构层只约定范围。各 edge 启用前必须先通过 §10.1 Phase 0.5 验收。

***

## 5. 推进路线（7 天作战图）

> 实际目标不是 7 天达 $50，而是 7 天内完成 Phase 0.5 → Paper → Live α 阶段并产出框架资产。$50 是右尾彩蛋。

### Day 0（2026-06-25 晚）— 设计 sign-off

- 本文档进入 audit-revision，完成 §18 审计闸门补强后再复审
- 建分支 `feat/v3-zero-data`
- 输出 `reports/v3_api_signoff.md` 与 `reports/v3_execution_feasibility.md`，通过后才允许进入 Day 1

### Day 1（2026-06-26）— 数据管道 + 高优先 edge 回测（A + B + E）

| 任务 | 文件 | 验收 |
|------|------|------|
| T1 OKX announcement fetcher | `src/data/okx_announcements.py` | 拉到 ≥ 6 个月历史公告 |
| T2 listing events builder | `src/data/okx_listing_events.py` | `listing_events.csv` ≥ 50 行 |
| T3 OKX funding/OI fetcher | `src/data/okx_funding.py` + `okx_oi.py` | 6 月 funding/OI 拉齐 |
| T4 Strategy base protocol | `src/backtest/strategies/base.py` | 协议定义 + 单元测试 |
| T5 listing_fade 实现 | `strategies/listing_fade.py` + `event_engine.py` | `reports/v3_A_listing_fade.md` |
| T6 funding_extreme 实现 | `strategies/funding_extreme.py` | `reports/v3_B_funding_extreme.md` |
| T7 pre_funding_unwind 实现 | `strategies/pre_funding_unwind.py` | `reports/v3_E_pre_funding.md` |
| T8 报告 1-3/7 | 上述三份 report | 各自 DECISION PASS/REPARAM/ABORT |

### Day 2（2026-06-27）— 中频 edge 回测（C + D + K + H）

| 任务 | 文件 | 验收 |
|------|------|------|
| T9 beta_decouple | `strategies/beta_decouple.py` | `reports/v3_C_beta_decouple.md` |
| T10 weekend_wick | `strategies/weekend_wick.py` | `reports/v3_D_weekend_wick.md` |
| T11 pair_mr | `strategies/pair_mr.py` + `pair_universe.json` | `reports/v3_K_pair_mr.md` |
| T12 oi_velocity | `strategies/oi_velocity.py` | `reports/v3_H_oi_velocity.md` |
| T13 横向汇总 | `reports/v3_phase0_combo.md` | 选 ≥ 3 条 PASS 进入 ensemble |

### Day 3（2026-06-28）— Ensemble + Paper trading

| 任务 | 验收 |
|------|------|
| T14 ensemble 仲裁层 | 信号冲突时按 priority 降序 + 同 entry_ts & symbol 去重 |
| T15 state_machine 实现 | 4 阶段递进 + 冷却 + DD 熔断 |
| T16 Paper runner | 24 小时纸面跑，比较实时数据与回测信号一致性 |
| T17 Paper 报告 | `reports/v3_paper.md`，确认 trade 频率、滑点假设 |

### Day 4（2026-06-29）— 实盘 $7 启动 · α 阶段

> **入场前 checklist：**
> - [ ] §18.2 API 签核通过，所有 live 字段 point-in-time 可得
> - [ ] §18.3 $7 执行可行性通过，A/E/H 至少 2 条在目标币种满足最小下单与止损精度
> - [ ] §18.4 至少 2 条 strategy 独立 PASS，且其中至少 1 条为 A 或 E
> - [ ] §18.5 ensemble 相关性与共同亏损检查通过
> - [ ] OKX API key 已验证有效 + IP 白名单
> - [ ] RiskGuard 单元测试通过
> - [ ] State machine 在 paper trading 上 24h 无报错
> - [ ] 监控告警已对接
> - [ ] 资金已划入 trading account
> - [ ] 先用 $0.5 名义仓位 echo test 验证下单/撤单/止损/平仓链路

| 任务 | 验收 |
|------|------|
| T18 echo test | 1 笔 $0.5 仓位下单 + 平仓，确认链路 |
| T19 切换 α 阶段 | state_machine 进入 α，启用设计 R |
| T20 滚动盯盘 | 当日复盘 |
| **当日目标** | 突破 $14（β 阶段） |

### Day 5-6（2026-06-30 - 07-01）— β/γ 阶段

- 推进至 $25-$30
- 复盘每笔 trade R 实现 vs 预期
- 若任何 strategy 实盘表现 < 回测胜率 -15pp，**当 strategy 立即下线**（不修，只下线）

### Day 7（2026-07-02）— 复盘 + 报告

| 任务 | 产出 |
|------|------|
| 整体复盘 | `reports/v3_live_week1.md` |
| 框架资产清单 | 哪些组件能直接拿到下一轮 |
| 失败/成功路径标注 | 决定是否进入"长期保留"模式 |

***

## 6. 验收闸门（决策表）

### 6.1 单 strategy 闸门（Phase 0.5）

每条 strategy 必须独立跑出以下 PASS：

| 指标 | A 上市 | B funding | C β | D 周末 | E pre-fund | K pair MR | H OI vel |
|------|--------|-----------|-----|--------|------------|-----------|----------|
| 样本数 | ≥ 30 | ≥ 80 | ≥ 60 | ≥ 40 | ≥ 60 | ≥ 100 | ≥ 60 |
| 胜率 | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% |
| EV(R) | ≥ +0.4 | ≥ +0.3 | ≥ +0.3 | ≥ +0.3 | ≥ +0.25 | ≥ +0.25 | ≥ +0.3 |
| PF | ≥ 1.5 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 |
| 最大连亏 | ≤ 5 | ≤ 6 | ≤ 6 | ≤ 6 | ≤ 6 | ≤ 6 | ≤ 6 |
| 频次 | ≥ 2/周 | ≥ 1/天 | ≥ 1/天 | ≥ 4/周 | ≥ 5/天 | ≥ 3/天 | ≥ 3/天 |

### 6.2 Ensemble 闸门

- ≥ 2 条 strategy 单独 PASS
- ensemble 90 天回测 EV ≥ +0.4R，PF ≥ 1.5
- 最大 DD ≤ 70%，最大连亏 ≤ 6
- 策略间日收益相关系数 ≤ 0.65；超过则保留 EV 更高的一条
- 同一 UTC 小时共同亏损占比 ≤ 35%；超过则增加互斥规则或下线
- macro 排除日分组不得出现 EV(R) 结构性转负

### 6.3 实盘上线闸门

- §18 审计闸门全部 PASS
- ensemble PASS
- Paper 24h 信号触发数与回测吻合度 ≥ 80%
- echo test 链路验证通过

### 6.4 实盘失败下线条件

任一触发即对应 strategy 下线（不修不补）：

- 该 strategy 实盘 10 笔后胜率 < 回测 -15pp
- 实盘单笔实现 R 与回测分布 KS test p < 0.05
- 出现回测中未观测到的 exit_reason 占比 > 20%

***

## 7. 失败处理（提前讲清退场仪式）

### 7.1 单 strategy ABORT

- 该 strategy 立即冻结，**不修不补**（修补只会带来过拟合）
- 进入下一 strategy 实验，不让单条失败拖整体

### 7.2 全部 strategy ABORT

- 输出 `reports/v3_post_mortem.md`
- 承认"**$7 量化在 2026 不成立**"
- 框架资产归档（Strategy 协议、OKX data pipeline、Paper/Live wrapper、state machine）
- 资金或退回钱包或留作下个 cycle 的种子

### 7.3 实盘爆仓

- 不补充资金
- 复盘 strategy vs state machine vs 滑点 vs 行情偏差 四个维度
- 决定是否进入"框架资产 + 暂停实盘"模式

### 7.4 部分成功

- 任一 strategy 实盘 PASS 但其它 FAIL → 在该 strategy 上继续，其它归档
- 达 $50 但未达 7 天 → 提现 $40，剩 $10 转入"轻仓继续模式"

***

## 8. 外部资源与文献参考

各 edge 的完整文献与经验依据已迁移至设计文档 §9（文献与经验依据）。
本节仅保留显式排除的资源清单和核心引用。

### 8.1 核心引用

- [Propfirm · 暴击流全解密](https://goodpropfirm.com/critical-strike/) — 语义校准原文
- [Yellow.com 2025 · Funding Rate Reversals](https://yellow.com/learn/how-to-read-funding-rates-crypto-reversals)
- [ScienceDirect 2025 · Funding Rate Arbitrage](https://www.sciencedirect.com/science/article/pii/S2096720925000818)
- [arxiv 2602.00776 · Crypto Microstructure](https://arxiv.org/html/2602.00776v1)
- [BitMEX · State of Crypto Perps 2025](https://www.bitmex.com/blog/state-of-crypto-perps-2025)

### 8.2 显式排除的资源

| 资源 | 排除原因 |
|------|----------|
| Coinglass / Tardis 付费 API | 已在 V2 死亡复盘中排除（成本结构不成立） |
| 中文社区"擒龙战法 / 庄家分析" | 已在 V2 §8 排除（无统计意义） |
| TradingView 公开 Pine 脚本 | 完全公共信号，无 edge |
| hummingbot | HFT 取向，与 200-400ms 延迟需求错配 |
| OKX `liquidation-orders` 单所 WS | 单所样本稀疏，会再造一份 Phase 0 同款噪声 |

***

## 9. 已知边界与不做事项

### 9.1 显式不做

- ❌ 不复活 V1（追清算）— 物理延迟决定必输
- ❌ 不付 Coinglass / Tardis — $7 资金 / $30+ 月费 = 长期 EV 负
- ❌ 不订阅 OKX 单所 liquidation-orders — 单所稀疏 + 与 Phase 0 同款噪声
- ❌ **不做现货** — 所有 edge 仅在 OKX 永续合约（SWAP）上执行
- ❌ **不做跨所交易腿** — 仅在 OKX 内下单
- ⚠️ **可读跨所信号（V3.1 起松绑）** — 允许第三所公告/价格作为入场依据，但下单 100% 在 OKX 永续
- ❌ 不做做市（MM）— 200-400ms 延迟无胜算
- ❌ 不做 grid / DCA / 套保
- ❌ 不动 `src/strategy.py` 与 `src/main.py` — 保留 V1 历史作对照
- ❌ 不在实盘启动前跳过 echo test
- ❌ 不在任何 strategy 实盘连续亏 3 笔后强行加仓"找回"

### 9.2 范围边界（V3 不解决的）

- 不解决数据中断的多源冗余（仅做 OKX 单源 + Binance 回测对照）
- 不解决 OKX 风控 / KYC / 封号风险（用户自担）
- 不解决跨周期资产配置（这是一个一次性 sprint）
- 不预测 macro 事件（CPI / FOMC 期间 strategy 自动暂停）

### 9.3 跨周期风险排除时段

- CPI / FOMC / NFP 公布前后 30 分钟
- BTC 当日波动 > 5% 的高 spillover 时段
- OKX 维护窗口（提前公告）

***

## 10. 附录 A：滑点与维持保证金建模 → 详见架构文档

滑点参数、交易成本建模、维持保证金率默认值已迁移至架构文档 §11（风险与约束）。
→ [`docs/architecture/2026-06-27-strategy-v3-execution-architecture.md`](../architecture/2026-06-27-strategy-v3-execution-architecture.md)

## 11. 附录 B：暴击流原则转译 → 详见架构文档

暴击流可操作纪律版本（重仓但单 R 锁死、止损一次到位、命中不眷恋、不补充资金、框架 > 单次结果）已迁移至架构文档 §6（暴击流仓位状态机）。
→ [`docs/architecture/2026-06-27-strategy-v3-execution-architecture.md`](../architecture/2026-06-27-strategy-v3-execution-architecture.md)

## 12. 附录 C：与既有文档的对位关系

| 既有文档 | V3 对位 | 处理方式 |
|----------|---------|----------|
| `docs/design/strategy_plan.md` (V1) | 已死 | 保留作对照，不动 src/strategy.py |
| `docs/design/strategy_plan_v2.md` (V2) | 已死 | V2 §3 Option B 升级为 V3 Strategy A |
| `docs/report/PHASE_0_REPORT.md` | 数据假设证伪 | 报告结论 §10 是 V3 入口 |
| `docs/plan/PHASE_0_EXECUTION.md` | Phase 0 执行规格 | 复用框架（验收阈值、目录布局、协议） |
| `docs/discussions/2026-06-25-okx-algo.md` | 三视角审计结论 | V3 是该结论"建议·立即"段的落地 |
| [`docs/design/2026-06-27-strategy-v3-edge-design.md`](../design/2026-06-27-strategy-v3-edge-design.md) | **V3 新增** | Edge 信号设计独立文档（信号定义、阈值、验证规则） |
| [`docs/architecture/2026-06-27-strategy-v3-execution-architecture.md`](../architecture/2026-06-27-strategy-v3-execution-architecture.md) | **V3 新增** | 共享执行架构独立文档（状态机、模块边界、数据流、熔断） |

***

## 13. 决策签收

**本设计的对外承诺：**

1. 先产出 API 签核与 $7 执行可行性报告，确认方案不是纸面可行
2. 7 天内产出 7 条 edge 的 Phase 0.5 回测报告；若 A/E 至少 1 条 + 任意另一条 strategy PASS，进入 ensemble
3. 至少 2 条 strategy 完成实盘验证（PASS 或明确 FAIL）
4. 输出可复用的 Strategy 协议 + OKX data pipeline + state machine 框架
5. §18 全部 PASS 后启动实盘 $7 暴击流；不达 $50 不补仓；爆仓即归档

**本设计的对内承诺：**

- 设计完成后先进入 audit-revision；复审通过后冻结，进入工程实施
- 实施过程中任何阈值变更必须记录到实施变更日志
- 7 条 strategy 任一回测 ABORT 即下线，不"修复"
- 实盘失败立刻进入 §7 退场仪式，不重新设计 V4 来"找补"

**等待签收：** §18 审计闸门复审通过 → 用户 sign-off → 开 `feat/v3-zero-data` 分支 → 进入 Day 1。

***

## 14. 审计修订闸门

本节是对 audit 文档与 PM 批注的响应。PM 明确要求当前阶段保持 $7 → $50 暴击流目标，因此本节不把 live α 降级为 1x dry-run；它只规定进入暴击流前必须完成的证据闸门。

### 14.1 状态语义

| 状态 | 含义 | 允许动作 |
|------|------|----------|
| `audit-revision` | 当前状态；方案正在按审核结论修订 | 允许改文档，不允许实盘 |
| `approved-for-research` | API 与执行可行性已通过，但 edge 尚未 PASS | 允许回测与 paper，不允许实盘 |
| `approved-for-gated-live` | §14.2-§14.5 全部 PASS | 允许 $7 → $50 live α |
| `rejected-for-live` | 任一硬闸门失败且无替代路径 | 禁止实盘，保留研究资产 |

### 14.2 API 签核闸门

输出文件：`reports/v3_api_signoff.md`。

| 数据 | PASS 标准 |
|------|-----------|
| instruments | SWAP 标的、lot size、tick size、ctVal、minSz 能覆盖候选 universe |
| announcements | 历史公告深度、分页、公告时间 → 能重建 ≥ 6 个月 listing events |
| candles | 1m 历史与 live WS 一致性，缺口 ≤ 0.5%，缺口可重拉 |
| funding | live 可见字段 vs settled history 区分；B/E 不使用事后不可见字段 |
| OI | endpoint、粒度、发布时间、延迟可实测 |
| max leverage | 只用于 live sizing，不用于历史伪造 |

任一数据源无法签核时，对应 strategy 自动禁用：funding 失败禁用 B/E；OI 失败禁用 H；announcements 失败禁用 A。

### 14.3 $7 执行可行性闸门

输出文件：`reports/v3_execution_feasibility.md`。

PASS 标准：

- A/E/H 至少 2 条策略的候选标的中，≥ 10 个 symbol 在 $7 equity 下可按设计 R 开仓并设置硬止损
- K 若进入 live，至少 6 个 pair 的双腿都满足最小下单；任一腿最小名义超过预算 80%，该 pair 禁用
- 回测必须按真实 lot/tick round 后的价格和数量计算 PnL；未做 round 的报告不得 PASS
- post-only 未成交率、撤单重挂成本、taker fallback 成本作为单独字段进入报告

### 14.4 单 edge 证据闸门

每条 edge 的报告必须来自真实历史数据，不允许 mock 或手工样例冒充。报告至少包含：

- `trades.csv`：逐笔交易，含 entry_ts、exit_ts、symbol、side、entry_price、exit_price、target_price、stop_price、exit_reason、pnl_R、price_pnl_R、fee_slippage_R、funding_pnl_R、equity_after
- `summary.json`：样本数、胜率、EV(R)、PF、最大 DD、最大连亏、交易频次、平均持仓、极值交易
- `sensitivity_grid.csv`：至少覆盖核心阈值 ±25%，ROBUSTNESS ≥ MEDIUM
- 分组表：按 symbol、UTC hour、weekday、macro excluded/non-excluded 分组
- 执行模拟：手续费、滑点、lot/tick round、post-only 未成交、taker fallback
- point-in-time 证据样本：每条依赖 funding/OI/announcement 的策略，报告必须附 ≥ 10 条 signal_ts 对应的原始 API 快照或缓存记录

进入 live 的最低组合：A 或 E 至少 1 条 PASS，且另有任意 1 条低相关 strategy PASS。若只有 K/H PASS 而 A/E 未 PASS，不允许启动 live α。

### 14.5 Ensemble 证据闸门

输出文件：`reports/v3_phase0_combo.md`。

PASS 标准：

- ≥ 2 条 strategy 单独 PASS，且满足 §14.4 的 A/E 主线要求
- ensemble EV ≥ +0.4R，PF ≥ 1.5，最大连亏 ≤ 6，最大 DD ≤ 70%
- 策略间收益相关系数 ≤ 0.65；超过则保留 EV 更高的一条
- 共同亏损小时占比 ≤ 35%；超过则增加互斥调度或禁用
- Monte Carlo 10,000 次路径中，破产概率、达 $14/$25/$50 的概率必须单独列示

### 14.6 PM 批注处理

PM 批注：不要把 live α 阶段降到 1x + 最小仓位 + dry-run comparison，当前阶段就是 $7 → $50 快速积累。

处理结论：采纳。echo test 只验证链路，不改变暴击流目标。作为交换，§14.2-§14.5 变成硬闸门：闸门不过，不是降杠杆实盘，而是禁止实盘。

### 14.7 流程说明

| 阶段 | 关键任务 | 产出 | 闸门 |
|------|----------|------|------|
| Phase 0 | 设计 sign-off、API 签核、执行可行性验证 | `v3_api_signoff.md`、`v3_execution_feasibility.md` | §14.2-§14.3 |
| Day 1 | 数据管道 + 高优先 edge 回测（A/B/E） | `v3_A/B/E_*.md` | §14.4 |
| Day 2 | 中频 edge 回测（C/D/K/H）+ 横向汇总 | `v3_phase0_combo.md` | §14.4 |
| Day 3 | Ensemble + State Machine + Paper | `v3_paper.md` | §14.5 |
| Day 4-7 | 实盘 $7 → $50 | `v3_live_week1.md` | §14 全部闸门 |

***

## 15. 实施变更日志

> 根据 §13 对内承诺，实施过程中任何阈值或设计变更必须记录于此。

| 日期 | 变更 | 触发原因 | 影响范围 | 状态 |
|------|------|----------|----------|------|
| 2026-06-26 | **移除 `EnsembleStrategy.min_equity`** — 取消 $7 最低权益闸门，子策略产生信号后直接进入 ensemble 仲裁 | 实盘权益 $6.24 低于 $7.0 门槛，所有信号被静默丢弃 | `ensemble.py`: 移除 `min_equity` 字段；`resolve_conflicts` 不再检查权益 | 已实施 |

***

> 一句话总结：V3.1 不是 V2 的修补，是 V1/V2 死亡后唯一三维（资金/数据/延迟）同时成立的路径——再叠加频次扩频（A 单线 → 7 edge 组合），把 $7 当一颗有限子弹的右尾打，把框架当真正的资产留下。
