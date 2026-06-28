# OKX-Bot V3 — Edge 信号设计（Zero-Data-Cost 暴击流组合）

> 本文档独立提取自 `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md`，只保留 edge 层面的信号定义、阈值、验证规则与风险控制。执行排期、架构工程、共享状态机等内容请参见原方案文件与架构文档。
>
> 版本：V3.1 · 7 条 edge（A/B/C/D/E/K/H）· 设计时间：2026-06-27

---

## 1. 背景

本设计文档的诞生背景：V3 方案文件（~1241 行）同时混合了 edge 设计方案、工程架构、执行排期、审计闸门、决策上下文等多重内容，导致阅读与引用困难。根据 `docs/design/` 的职责定位（模块级方案设计、接口设计、数据模型设计、算法流程、业务规则），将 edge 信号设计独立成文。

### 1.1 前提硬约束

任何 edge 必须同时满足以下三维才可能入选：

| 维度 | 数值 | 含义 |
|------|------|------|
| 资金 | **$7** | 任何 ≥ $5/月固定订阅都让 EV 长期为负 |
| 数据预算 | **$0/月** | Coinglass / Tardis 全部出局；仅用 OKX + Binance 免费公共 API |
| 网络延迟 | **200-400ms** | 信号尺度 ≥ 1 分钟才能容忍；sub-second 类策略物理出局 |

### 1.2 Edge 来源概述

所有 edge 的共同根源：**散户结构性行为偏差**（FOMO、拥挤多头、薄盘流动性）。不依赖清算数据、不依赖付费数据源。

---

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| 信号覆盖度 | 7 条 edge 合计 setup 频率达到 80-150/周（研究假设，需回测实证） |
| 单 edge EV | 单笔 EV 维持在 +0.25R ~ +0.5R 区间 |
| 暴击流适配 | 每条 edge 的 1R 定义与仓位公式与暴击流状态机兼容 |
| 数据零成本 | 全部信号仅用 OKX REST/WS 公开接口 + Binance 公开数据 |
| 延迟容忍 | 信号在 1m bar 尺度上稳定，200-400ms 延迟不破坏入场窗口 |

---

## 3. Edge 准入准则

候选 edge 进入设计前必须全部满足以下 6 条准入准则。任一不满足即出局：

1. **散户行为根源**：edge 依赖散户结构性行为偏差（FOMO、拥挤多头、薄盘流动性）；机构主导/套利已收敛的 edge 全部出局。
2. **数据 $0 成本**：仅用 OKX 公开 REST/WS + Binance 公开数据。
3. **延迟容忍 ≥ 1 分钟**：信号在 1m bar 尺度上稳定，200-400ms 延迟不破坏入场窗口。
4. **OKX 永续可执行**：标的在 OKX SWAP 上，且 leverage cap 允许 ≥ 5x。
5. **频次匹配**：事件型 edge ≥ 1 笔/周，连续/MR 型 ≥ 1 笔/天。
6. **证据闸门**：进入 ensemble 或 live 前，必须产出真实回测报告（样本数、胜率、EV(R)、PF、最大连亏、交易成本、滑点敏感性、参数敏感性、按 symbol/hour 分组）。

---

## 4. Edge 清单与定义

### 4.1 总览

| ID | 名称 | 类型 | Edge 根源 | 频率假设 | 杠杆上限 | 1R |
|----|------|------|-----------|----------|----------|-----|
| **A** | OKX 新合约上市 Fade | 事件型 | 散户公告 FOMO + OKX 新上市 leverage 收紧 trap 多头 | ≥ 2 笔/周 | 5-10x | 30% |
| **B** | Funding Rate 极值反转 | 连续/MR | 杠杆方向过度集中后 unwind | ≥ 1 笔/天 | 6-8x | 20% |
| **C** | BTC-Alt β Decoupling Reversion | 连续/MR | BTC 不动时 alt 单边情绪偏离均值回归 | ≥ 1 笔/天 | 8-10x | 20% |
| **D** | 周末低流动性 Wick Fade | 事件型 | UTC 周末薄盘 wick 后回归 | ≥ 4 笔/周 | 5-7x | 15% |
| **E** | Pre-funding Settlement Unwind | 连续/MR | funding 结算前拥挤方向 preemptive close → MR | ≥ 5 笔/天 | 6-8x | 18% |
| **K** | 同主题 Alt Pair MR | 连续/MR | narrative 桶内 alt pair 短期均值回归 | ≥ 3 笔/天 | 8-10x | 15% |
| **H** | OI Velocity + 价格滞涨 | 连续/MR | OI 累积 + 价格未跟随 → 库存堆积后爆发 fade | ≥ 3 笔/天 | 8-10x | 18% |

### 4.2 辅助信号（Ensemble 加权层）

| ID | 名称 | 数据 | 用途 |
|----|------|------|------|
| L | Long/Short Ratio 极值反转 | OKX position info | 散户拥挤 contrarian，与 funding/OI 同向时 ensemble 加权 |

### 4.3 Backlog（V3.2 候选）

| ID | 名称 | 说明 |
|----|------|------|
| G | 第三所上市公告 spillover | Binance/Coinbase 上市 → OKX 同币 momentum 后 fade；§13.1 跨所信号已松绑，但需 firehose 噪声管理 |

---

## 5. 信号与阈值

### 5.1 Strategy A：OKX 新合约上市 Fade

**核心假说**：OKX 永续上市 0-30 分钟内 IV 与单边情绪极高，散户公告后 FOMO 推升价格 → 后续抛压。同时 OKX 对新上市永续自动收紧 leverage 至 3-5x，结构上限制了多头加杠杆能力，反向 fade 具备非对称 R:R。

**数据来源**：全部 OKX REST 免费。

| 数据 | Endpoint | 频率 |
|------|----------|------|
| 上市公告 | `/api/v5/support/announcements?annType=announcements-new-listings` | 每 5 分钟 |
| 全量合约清单 | `/api/v5/public/instruments?instType=SWAP` | 每日 diff |
| 1m kline | `/api/v5/market/candles?bar=1m` | WS subscribe / REST |
| Leverage cap | `/api/v5/account/max-leverage?instId={}` | 上市时实测 |

#### A1：Pump-then-Fade（主入场）

记号：上市时刻 $t_0$，$t_0$ 后第 $i$ 根 1m bar 的 OHLC 为 $(O_i, H_i, L_i, C_i)$。

| 条件 | 表达式 | 阈值 |
|------|--------|------|
| C1 已 pump | $\max(H_0, \ldots, H_4) / O_0 \geq 1.15$ | 上市后 5min 涨幅 ≥ 15% |
| C2 5m bar 形态确认 | $\sum_{i=0..4} vol_i$ ≥ 该币种 24h 均量 | 流动性确认 |
| C3 回踩区间 | $H \times 0.85 \leq P_{now} \leq H \times 0.88$ | 回踩 12-15% |
| C4 回踩动能减速 | 1m bar 收阴 + volume 较 pump 期回落 ≥ 50% | 抛压减速 |
| C5 leverage cap | $L_{OKX} \geq 5$ | 没杠杆就放弃 |

- **方向**：优先做空（多头被 leverage cap 锁死）
- **入场**：post-only limit SELL at $P_{now}$；未成交在 2 分钟内放弃
- **目标**：$O_0 \pm k \times ATR_{5m}$，默认 $k = 0.5$，方向 return-to-open
- **硬止损**：$H \times 1.02$（破前高 2%）
- **时间止损**：入场后 30 分钟
- **1R**：α 阶段 30%，β 阶段 20%

#### A2：Echo / Re-pump Fade

适用场景：A1 未触发或已止损出场，但同一上市事件在 15-60 分钟窗口内出现"二次冲高"。

| 条件 | 表达式 | 阈值 |
|------|--------|------|
| C1 1st pump 已发生 | $H_1 / O_0 \geq 1.15$ | A1 入场前提 |
| C2 2nd 次高未破前高 | $0.85 \leq H_2 / H_1 < 1.00$ | 二次冲高但弱于首峰 |
| C3 动能衰减 | $vol(H_2 \pm 2min) / vol(H_1 \pm 2min) \leq 0.70$ | 接力意愿弱 |
| C4 funding 转正/上行 | funding rate 较 $H_1$ 时刻上行 ≥ 50% 或 z 转正 | 多头加仓证据 |
| C5 leverage cap | $L_{OKX} \geq 5$ | 同 A1 |

- **入场**：post-only limit SHORT at $H_2 \times [0.985, 0.99]$
- **目标**：返回 $H_1$ 与首峰后 swing low 之间的中位价 $\pm 0.5 \times ATR_{5m}$
- **硬止损**：$H_1 \times 1.005$（比 A1 更紧）
- **时间止损**：入场后 20 分钟
- **入场预算**：单上市事件 A1 + A2 合计入场次数 ≤ 3；A1 当前在仓则 A2 自动跳过

---

### 5.2 Strategy B：Funding Rate 极值反转

**核心假说**：funding rate 偏离 30 天 rolling z-score ≥ +2.5σ（多头过度拥挤），同时 OI/24h-volume 比值处于 P80 以上 → 持仓成本累积压力 → unwind 触发均值回归。

| 条件 | 表达式 | 阈值 |
|------|--------|------|
| C1 funding 极值 | `abs(funding_z) ≥ 2.5` | z-score 单尾 |
| C2 OI 拥挤 | `oi_pct > 0.80` | 杠杆库存确认 |
| C3 价格未跟随 | `sign(price_1h_return) ≠ sign(funding_z)` | 提前 unwind 苗头 |
| C4 流动性 | 24h volume ≥ $20M | |

预处理：

```
funding_z(t) = (funding(t) - mean(funding, 30d)) / std(funding, 30d)
oi_pct(t)    = percentile_rank(oi/24h_vol, 30d)
```

- **方向**：`signal = -sign(funding_z)`。多头拥挤 → 做空，空头拥挤 → 做多
- **入场**：post-only limit at mid
- **目标**：funding 回归至 `abs(funding_z) ≤ 0.5`
- **硬止损**：反向 1.5 × ATR(4h)
- **时间止损**：3 × funding 周期 = 24h
- **杠杆**：6-8x；**1R** = 20% equity

**已知风险**：强趋势期 funding 可持续高（CoinGecko 2024 BTC 案例）。执行成本被 fee-only 回测显著高估。

---

### 5.3 Strategy C：BTC-Alt β Decoupling Reversion

**核心假说**：当 BTC 60 分钟 realized vol 处于 30 天 P30 以下（BTC 近乎静止），但某 alt 60 分钟 z-score 偏离 ≥ 2.5σ → alt 偏离来自内部杂音/散户情绪 → 60 分钟内 mean reversion 概率高。

```
btc_rv_pct = percentile_rank(realized_vol(BTC, 60m), 30d)
alt_z      = (close - vwap(alt, 60m)) / std(close, 60m)
```

| 条件 | 阈值 |
|------|------|
| C1 BTC 静止 | `btc_rv_pct < 0.30` |
| C2 alt 偏离 | `abs(alt_z) ≥ 2.5` |
| C3 alt 流动性 | 24h volume ≥ $10M |
| C4 alt 非新币 | 上市 ≥ 30 天（避免与 A 重叠） |

- **方向**：`signal = -sign(alt_z)`，反向 fade
- **目标**：alt 偏离回归 50%（z 从 ±2.5 回到 ±1.25）
- **硬止损**：alt 偏离的 1.2 倍（z 走到 ±3.0）
- **时间止损**：90 分钟
- **杠杆**：8-10x；**1R** = 20% equity

---

### 5.4 Strategy D：周末低流动性 Wick Fade

**核心假说**：周末 UTC Fri 22:00 - Sun 22:00 全市场 perp 流动性下降 30-50%（BitMEX State of Perps 2025）。薄盘下大单制造 wick，wick 后 1-2 小时内回归 5m bar 中位数概率高。

```
in_window = UTC weekday in [Fri 22:00, Sun 22:00]
bar_range = (high_5m - low_5m)
wick_threshold = 0.95 quantile of (price - vwap_5m) over rolling 7d 同时段
```

| 条件 | 阈值 |
|------|------|
| C1 时间窗口 | `in_window == True` |
| C2 wick 触发 | 1m close 在 5m bar range 0.95 quantile 之外 |
| C3 wick 回弹 | 紧接的 1m bar 反向 ≥ wick 距离的 30% |
| C4 流动性 | 该币种 24h volume ≥ $5M |

- **方向**：fade wick 方向，回归 5m bar 中位数
- **目标**：返回 5m bar 中位数
- **硬止损**：1.0 × ATR(5m) 反向
- **时间止损**：60 分钟
- **杠杆**：5-7x（周末样本少 + 外溢风险）；**1R** = 15% equity

---

### 5.5 Strategy E：Pre-funding Settlement Unwind

**核心假说**：OKX 永续 funding 每 8h 结算（UTC 00:00 / 08:00 / 16:00）。结算前 30-60 分钟内，若某币 funding z-score 极值 + OI 高位 + 价格已开始反向 → 拥挤方向 preemptive close 避免下一期 funding 成本 → mean reversion。

**与 B 的核心区别**：B 是"funding 极值后 24h 内反转"——慢节奏；E 是"结算前 30-60 分钟"——micro window，触发更精准、止损更紧、频次更高。E 在 B 基础上叠加时段窗口 + 反向价格证据两个加强约束。

**点时可得性要求**：E/B 回测必须区分 `live 可见 funding` 与 `事后 settled funding history`。若 OKX 只能返回 settled funding，E 必须使用 next funding / predicted funding 字段，否则判定 lookahead bias，策略 ABORT。

```
funding_z(t)    = (funding(t) - mean(funding, 30d)) / std(funding, 30d)
oi_z(t)         = (oi/24h_vol(t) - mean, 30d) / std, 30d
price_delta(t)  = price(t) - price(t - 30min)
```

| 条件 | 表达式 | 阈值 |
|------|--------|------|
| C1 时段窗口 | `t ∈ [settlement - 60min, settlement - 5min]` | 硬窗口（3 次/天）|
| C2 funding 极值 | `abs(funding_z) ≥ 2.0` | 比 B 的 2.5 略松 |
| C3 OI 拥挤 | `oi_z ≥ 1.5` | 杠杆库存确认 |
| C4 价格已反向 | `sign(price_delta) ≠ sign(funding_z)` | "聪明钱"已先动 |
| C5 流动性 | 24h volume ≥ $10M | |

- **方向**：`signal = -sign(funding_z)`，反向 fade
- **入场**：post-only limit at mid
- **目标**（满足其一即出）：结算后 API 已发布 settled funding 且 `|z| ≤ 1.0`；或价格已 mean revert 50%
- **硬止损**：1.0 × ATR(1h)
- **时间止损**：结算后 30 分钟（整个窗口最多持仓 90 分钟）
- **杠杆**：6-8x；**1R** = 18% equity
- **funding cashflow 建模**：所有跨结算时点持仓必须把实际 funding payment 计入 PnL，输出 `price_pnl_R`、`funding_pnl_R`、`fee_slippage_R` 三列。若 funding cashflow 缺失，E/B 报告不得 PASS。

---

### 5.6 Strategy K：同主题 Alt Pair MR

**核心假说**：crypto 内存在 narrative 桶。先用统计检验筛出稳定 pair，再在该 pair 的 log-ratio z-score 偏离 ≥ 2σ 时做短期 MR。只有当 pair 通过 cointegration 与 half-life 筛选、且桶内整体动量保持中性时，z-score 回归概率才足够高。

#### Pair 准入检验

每个候选 pair 在进入信号计算前必须通过以下全部筛选：

| 检验 | 阈值 | 失败处理 |
|------|------|----------|
| ADF on ratio | p-value ≤ 0.05 | 该 pair 禁用 |
| Engle-Granger | p-value ≤ 0.05 | 该 pair 禁用 |
| half-life | 10min ≤ half-life ≤ 360min | 过短视为噪声，过长不适合 90min 持仓 |
| rolling corr 稳定性 | 30d rolling corr P25 ≥ 0.50 | 相关结构不稳，禁用 |
| structural break | 最近 7d beta drift ≤ 30d beta 的 2σ | narrative 切换，禁用 7 天 |

#### 标的 Universe

| 桶 | 标的（OKX 永续） | Pair 候选数 |
|----|-----------------|-------------|
| AI | FET, RNDR, TAO, AGIX | C(4,2)=6 |
| L2 | ARB, OP, MATIC, STRK | 6 |
| DeFi | UNI, AAVE, COMP, LDO | 6 |
| Memes | DOGE, SHIB, WIF, PEPE | 6 |
| 其它 | 按 OKX 实际上线追加 | |

总 pair 候选 ~24-40。通过准入检验后的可交易 pair 数以实测为准；若通过数 < 6，K 不进入 ensemble。

#### 信号定义

预处理（每个 pair）：

```
ratio(t)        = log(price_A(t) / price_B(t))
hedge_beta(t)   = rolling_ols(log(price_A), log(price_B), 30d)
spread(t)       = log(price_A(t)) - hedge_beta(t) * log(price_B(t))
ratio_mean(t)   = rolling_mean(spread, 7d) on 1h bar
ratio_std(t)    = rolling_std(spread, 7d) on 1h bar
ratio_z(t)      = (ratio(t) - ratio_mean) / ratio_std
bucket_momentum = mean(60min log_returns, all bucket alts)
```

| 条件 | 表达式 | 阈值 |
|------|--------|------|
| C0 pair 准入 | §Pair 准入检验全部通过 | 不通过不开仓 |
| C1 z-score 偏离 | `abs(ratio_z) ≥ 2.0` | |
| C2 桶内动量过滤 | `abs(bucket_momentum) ≤ P50(30d)` | 排除桶级一致大涨大跌 |
| C3 两腿流动性 | 24h volume A 与 B 均 ≥ $5M | |
| C4 两腿不在 A/E 窗口内 | 两腿都不在 OKX 新上市 30 天内、不在 E 结算窗内 | 避免 strategy 冲突 |

- **方向**：`ratio_z > 0` → SHORT A + LONG B；`ratio_z < 0` → LONG A + SHORT B
- **入场**：两腿同时 post-only limit at mid；任一腿 3 分钟未成交 → 立即平已成交腿
- **目标**：`abs(ratio_z) ≤ 0.5` → 两腿同时平
- **硬止损**：`abs(ratio_z) ≥ 3.0` → 立刻双腿平
- **时间止损**：90 分钟
- **杠杆**：8-10x；**1R** = 15% equity（两腿合计）
- **单腿 notional**：取 `(1R × leverage) / 2`；R 校验按双腿合计 PnL = -1R × equity 判定

**已知风险**：narrative 转换让 cointegration 崩溃；两腿管理增加执行复杂度；双边手续费翻倍 → EV(R) 阈值放宽至 +0.25。

---

### 5.7 Strategy H：OI Velocity + 价格滞涨

**核心假说**：1h 内 OI 涨幅 > P95 但同期价格变动 < P30 → 仓位累积但无方向共识，杠杆库存堆积。下一根 5-15 分钟 bar 的单边爆发概率高，爆发后散户接力意愿弱 → fade 爆发回归。

**两阶段状态机**：

#### Stage 1（Pre-burst 监测，不入场）

```
oi_available_ts = oi_bar_close_ts + measured_publish_delay
oi_velocity(t)  = (oi_available(t) - oi_available(t - 60min)) / oi_available(t - 60min)
price_delta(t)  = abs(close(t) - close(t - 60min)) / close(t - 60min)
oi_v_pct(t)     = percentile_rank(oi_velocity, 30d, same symbol)
price_d_pct(t)  = percentile_rank(price_delta, 30d, same symbol)
```

| 条件 | 表达式 | 阈值 |
|------|--------|------|
| C1 OI 累积 | `oi_v_pct ≥ 0.95` | top 5% OI velocity |
| C2 价格滞涨 | `price_d_pct ≤ 0.30` | bottom 30% 价格变动 |
| C3 流动性 | 24h volume ≥ $10M | |

满足 → 进入"等待爆发"状态（最长 30 分钟）。

#### Stage 2（Fade Entry）

| 条件 | 表达式 | 阈值 |
|------|--------|------|
| C4 爆发触发 | 5-15min 内 `abs(price_5min_return) ≥ 1.5 × ATR(5m)` | 单边爆发 |
| C5 爆发动量减速 | 紧接的 1m bar volume 较爆发 1m bar 衰减 ≥ 30% | 接力意愿弱 |

- **方向**：`signal = -sign(price_5min_return)`，反向 fade 爆发
- **入场**：post-only limit at mid，2 分钟未成交放弃
- **目标**：爆发前价格 ± 0.3 × ATR(5m)
- **硬止损**：爆发延续方向 1.0 × ATR(5m)
- **时间止损**：入场后 15 分钟
- **杠杆**：8-10x；**1R** = 18% equity

**时序要求**：回测必须模拟 `bar close → API 数据发布 → 本地轮询 → 特征计算 → 下单` 的延迟链。默认保守延迟 65 分钟；未加入延迟的 H 回测结果无效。

**已知风险**：OI 数据 1h 粒度滞后 → Stage 1 实时判断有 ~30min 滞后；爆发可能不 MR 而延续（macro 驱动） → 硬止损一刀切，排除时段规则适用。

---

## 6. Ensemble 与冲突消解

### 6.1 信号冲突仲裁

同 bar 多 strategy 同时触发的冲突规则：

1. **按 priority 降序**：事件型（A > D）> 微观结构型（H > E）> MR 型（B > C > K）
2. **同 entry_ts & symbol 去重**：同一标的同一时间只允许一个 strategy 开仓
3. **互斥规则**：
   - A 与 E 在同标的不能同时开仓
   - K 两腿标的不能与其它 strategy 冲突（K 已通过 C4 条件规避 A/E 窗口）
4. **辅助信号 L 加权**：Long/Short 比率极值（> 70% 或 < 30%）与 funding/OI 同向时，对应方向信号在 ensemble 仲裁中获得加权优先

### 6.2 相关性与共同亏损控制

| 规则 | 阈值 | 处理 |
|------|------|------|
| 日收益相关系数 | ≤ 0.65 | 超过则保留 EV 更高的 strategy |
| 同一 UTC 小时共同亏损 | ≤ 35% | 超过则增加互斥规则或下线相关策略 |
| macro 排除日分组 | EV(R) 不出现结构性正转负 | 出现则审查该策略的分布偏移 |

### 6.3 辅助信号 L 的 ensemble 用法

L（Long/Short Ratio）仅作为 ensemble 加权层，不单独开仓：

- 当 L 信号方向与 strategy A/B/E/H 的入场方向一致时 → +3 priority 加权
- 当 L 信号方向相反时 → 不阻塞，但记录负加权信号供复盘

---

## 7. Edge 验证与监控

### 7.1 单 Edge 验收闸门

每条 strategy 独立回测必须 PASS 以下阈值（Phase 0.5）：

| 指标 | A | B | C | D | E | K | H |
|------|---|---|---|---|---|---|---|
| 样本数 | ≥ 30 | ≥ 80 | ≥ 60 | ≥ 40 | ≥ 60 | ≥ 100 | ≥ 60 |
| 胜率 | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% | ≥ 55% |
| EV(R) | ≥ +0.4 | ≥ +0.3 | ≥ +0.3 | ≥ +0.3 | ≥ +0.25 | ≥ +0.25 | ≥ +0.3 |
| PF | ≥ 1.5 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 | ≥ 1.4 |
| 最大连亏 | ≤ 5 | ≤ 6 | ≤ 6 | ≤ 6 | ≤ 6 | ≤ 6 | ≤ 6 |
| 频次 | ≥ 2/周 | ≥ 1/天 | ≥ 1/天 | ≥ 4/周 | ≥ 5/天 | ≥ 3/天 | ≥ 3/天 |

### 7.2 Ensemble 闸门

- ≥ 2 条 strategy 单独 PASS（其中 A 或 E 至少 1 条）
- ensemble 90 天回测 EV ≥ +0.4R，PF ≥ 1.5，最大连亏 ≤ 6，最大 DD ≤ 70%
- 策略间收益相关系数 ≤ 0.65
- 共同亏损小时占比 ≤ 35%

### 7.3 实盘运行中监控

| 触发条件 | 处理 |
|----------|------|
| 策略实盘 10 笔后胜率 < 回测 -15pp | 该 strategy 立即下线，不修不补 |
| 实盘单笔实现 R 与回测分布 KS test p < 0.05 | 该 strategy 立即下线 |
| 出现回测中未观测到的 exit_reason 占比 > 20% | 该 strategy 立即下线 |
| 连续 2 笔 -1R | 冷却 30 分钟 |
| 连续 3 笔 -1R | 冷却 12 小时 + 该 strategy 当日停 |
| 单日 DD ≥ 50% | 当日全停手 |

---

## 8. 风险与限制

### 8.1 Edge 层面风险

| Risk | 影响 edge | 缓解 |
|------|-----------|------|
| 强趋势期 funding 持续高 | B/E | 硬止损一刀切；C3 价格未跟随条件做二次筛选 |
| narrative 转换让 cointegration 崩溃 | K | 90 天 rolling 重新筛 pair universe |
| OI 数据 1h 粒度滞后 | H | 回测模拟 ~30min 滞后；Stage 1 等待窗口已包含滞后余量 |
| 周末样本少 + 外溢风险 | D | 杠杆降至 5-7x；1R 降至 15% |
| 上市事件稀疏 | A | 仅作事件主线，不单独依赖；E/K/H 做频次主力 |
| 双边手续费翻倍 | K | EV(R) 验收阈值放宽至 +0.25 |

### 8.2 显式不做的交易行为

- ❌ 不做现货（spot）——所有 edge 仅在 OKX 永续（SWAP）上执行
- ❌ 不做跨所交易腿——下单 100% 在 OKX；Binance/其它所数据仅作信号源
- ❌ 不做做市（MM）——200-400ms 延迟无胜算
- ❌ 不做 grid / DCA / 套保
- ❌ 不在任何 strategy 实盘连续亏 3 笔后强行加仓"找回"（马丁格尔化）
- ❌ 不付 Coinglass / Tardis 数据费

### 8.3 必须排除的时段

| 时段 | 影响 edge | 行为 |
|------|-----------|------|
| CPI / FOMC / NFP 公布前后 30 分钟 | 全部 | 暂停信号 + 已有持仓平仓 |
| BTC 当日波动 > 5% | 全部 | 暂停信号 |
| OKX 维护窗口 | 全部 | 提前公告，暂停 |

### 8.4 滑点与交易成本建模

| 项目 | 默认值 | 说明 |
|------|--------|------|
| OKX taker fee | 0.05% | 官方费率 |
| OKX maker fee | 0.02% | post-only 入场 |
| 滑点 per side（普通 alt） | 0.03% | Phase 0 默认 |
| 滑点 per side（新上市/wick） | 0.10% | 极端时段上调 |
| 维持保证金率 | 0.5%-1.5% | 按 OKX 实时拉取 |

---

## 9. 文献与经验依据

| Edge | 来源 |
|------|------|
| A | OKX 学习中心 alt pump 节奏 + GitHub okx-exchange 上市自动挂单工具广泛存在 |
| B / E | Yellow.com 2025 funding 反转、ScienceDirect 2025 funding arbitrage；E 是 B 的 micro-window 结算前版本 |
| C / K | arxiv 2602.00776 microstructure cross-asset 短期 reversion；K 需 ADF / Engle-Granger / half-life 三项筛选 |
| D | BitMEX State of Perps 2025 + 周末薄盘观察 |
| H | OI 累积 leading indicator 在 arxiv 2602.00776 与 funding/OI fragility 文献中均有论证 |
| L | Coinglass Long/Short Ratio 免费层；需与 funding/OI 同向才构成 ensemble 加权 |

---

## 10. 变更历史

| 日期 | 变更 | 触发原因 |
|------|------|----------|
| 2026-06-27 | 从 V3 方案文件独立提取为本设计文档 | 方案文件过于厚重（1241 行），edge 设计信息与执行排期/工程架构耦合 |
| 2026-06-26 | **移除 `EnsembleStrategy.min_equity`** | 实盘权益 $6.24 低于 $7.0 门槛导致所有信号被静默丢弃 |
| 2026-06-25 | 新增 E/K/H 三条 edge（V3.0 → V3.1） | V3.0 的 A/B/C/D 4 条 edge 合计 ~22-28 setup/周偏薄 |
| 2026-06-25 | 松绑 §13.1 跨所信号限制 | 允许第三所公告/价格作为入场依据，但交易腿 100% 锁 OKX 永续 |

---

> 本文档由 `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md` 独立提取，保持与方案文件的一致性。任何 edge 层面的阈值或信号变更必须同步更新本设计与方案文档。

---

## 相关文档

- [执行计划：V3.1 暴击流组合](../plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md) — 执行排期、验收闸门与审计决策
- [共享执行架构](../architecture/2026-06-27-strategy-v3-execution-architecture.md) — 模块边界、数据流、暴击流状态机与熔断
- [漂移分析报告](../reports/2026-06-27-live-echo-drift-analysis-report.md) — 代码与文档偏差的实际证据
- [Live Echo Runner 设计](../design/2026-06-26-live-echo-runner.md) — 当前实盘运行器的设计基线
