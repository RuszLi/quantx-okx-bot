# Strategy V3 共享执行架构

> **文档定位：** V3 暴击流多 edge 组合策略的共享运行时架构。定义模块边界、数据流、状态模型、持久化契约与外部集成约定，与 edge 具体的信号逻辑解耦。
>
> **版本：** v1
> **日期：** 2026-06-27
> **状态：** 定稿

---

## 1. 背景

V3 策略计划（`docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md`）混合了三类关注点：共享执行架构、edge 信号定义与阈值、工程实施排期。其中共享执行架构在 7 条 edge 间完全复用，不应随 edge 增删而改动。

本文件将共享部分独立为架构基线，使其成为 `docs/design/` 下 edge 设计文档与 `docs/plans/` 下实施文档的共同参考点。

### 1.1 相关文档

- **策略约束基线：** `strategy-and-factor-constraints.md` — 硬件延迟、数据预算、策略选型边界
- **可运行 Edge 设计：** `docs/design/2026-06-26-live-echo-runner.md` — C/D ensemble 实盘最小运行器
- **Edge 蓝图与排期：** `docs/plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md`
- **OKX 集成规范：** `okx-sdk-rules.md`、`sys-proxy-rules.md`

### 1.2 V3 架构总览

V3 执行系统由三层组成：

```
┌─────────────────────────────────────────────────────┐
│                    Edge Layer                        │
│  (listing_fade / funding_extreme / beta_decouple /   │
│   weekend_wick / pre_funding_unwind / pair_mr /      │
│   oi_velocity)                                       │
├─────────────────────────────────────────────────────┤
│              Ensemble Arbitration Layer              │
│  (信号冲突消解、按 strategy priority 排队)                │
├───────────────────┬─────────────────────────────────┤
│  Paper Runner     │   Live Runner                   │
│  (DRY-RUN 模式)    │   (实盘下单，复用 okx_client.py)    │
├───────────────────┴─────────────────────────────────┤
│           Critical Strike State Machine               │
│  (4 阶段递进、仓位计算、冷却、DD 熔断)                      │
├─────────────────────────────────────────────────────┤
│           RiskGuard (全局熔断)                         │
├─────────────────────────────────────────────────────┤
│   Data Layer (pipeline) / Persistence (CSV+JSON)    │
└─────────────────────────────────────────────────────┘
```

---

## 2. 架构目标

### 2.1 核心原则

| 原则 | 含义 |
|------|------|
| **edge 与执行解耦** | 每条 edge 只关心 `compute_signals()` 实现，不触碰下单、仓位管理、持久化 |
| **R 单位一致** | 所有 edge 的期望以 R 计量（`R = risk_per_trade_R × equity`），回测与实盘计量方式一致 |
| **共享骨架不变** | `Strategy` protocol、`EnsembleStrategy`、`CriticalStrikeStateMachine`、`RiskGuard` 是跨 edge 共享的，不随 edge 参数改动 |
| **zero-data-cost** | 所有数据源来自 OKX 与 Binance 公开免费 API；回测与 live 使用同一数据契约 |

### 2.2 非目标

- 不定义 edge 信号生成逻辑或参数阈值
- 不包含项目实施时间线或里程碑
- 不包含具体风控数值（由 `docs/design/` 中各 edge 文档提供）

---

## 3. 模块边界

```
src/
├── okx_client.py                  ← OKX REST + WebSocket（订单执行、账户查询）
├── okx_sdk.py                     ← python-okx SDK 封装（market_api / trade_api / account_api）
│
├── backtest/                      ← 回测框架层（Phase 0 骨架复用）
│   ├── engine.py                  ← bar-driven 回测引擎
│   ├── event_engine.py            ← 事件驱动回测引擎（用于 A）
│   ├── strategies/
│   │   ├── base.py                ← Strategy protocol（§4）
│   │   └── ensemble.py            ← 信号仲裁层
│   └── metrics.py                 ← 回测指标计算
│
├── paper/
│   ├── pipeline.py                ← 共享信号管道（数据获取 + 特征构造 + ensemble 调度）
│   └── runner.py                  ← Paper trading WAR
│
├── live/
│   ├── runner.py                  ← 实盘运行器骨架
│   ├── state_machine.py           ← 暴击流仓位状态机（§6）
│   └── risk_guard.py              ← 全局熔断（§7）
│
└── data/                          ← fetcher 模块（按数据源分类）
    ├── okx_announcements.py       ← 上市公告轮询
    ├── okx_funding.py             ← funding rate history
    ├── okx_oi.py                  ← open interest
    └── okx_listing_events.py      ← 6 个月历史上市事件 builder
```

### 3.1 层职责

| 层 | 模块 | 职责 | 不做什么 |
|----|------|------|----------|
| **Edge** | `base.py` 约定的 `Strategy` 实现 | 计算信号、定义所需数据 | 不下单、不管理仓位、不持久化 |
| **仲裁** | `EnsembleStrategy` | 按 `priority` + `(entry_ts, symbol)` 去重 | 不修改信号方向或价格 |
| **运行** | `paper/runner.py` / `live/runner.py` | 执行信号：纸面记录或实盘下单 | 不参与信号计算 |
| **状态** | `CriticalStrikeStateMachine` | 4 阶段递进、冷却、阶段切换 | 不直接下单 |
| **熔断** | `RiskGuard` | DD 熔断、连续亏损熔断、日交易上限 | 不修改策略参数 |
| **管道** | `pipeline.py` | 数据获取 + 特征构造 + 信号调度 | 不包含 edge 逻辑 |
| **集成** | `okx_client.py` | OKX API 调用封装 | 不包含业务逻辑 |

### 3.2 文件边界规则（不可违反）

1. **Edge 模块禁止引用** `okx_client.py`、`runner.py`、`state_machine.py`、`risk_guard.py`、`data/` 下的 fetcher。edge 只能引用 `base.py` 的 `Strategy` protocol 和 `pandas`。
2. **`pipeline.py` 禁止包含** edge 具体阈值或信号生成逻辑。信号生成委托给各 edge 的 `compute_signals()` 方法。
3. **`state_machine.py` 禁止直接调用** OKX API。状态切换必须由 runner 在确认交易结果后再触发。
4. **`okx_client.py` 禁止包含** 策略逻辑、仓位规划、信号计算。

---

## 4. Data Flow

### 4.1 回测数据流

```
Backtest Engine (bar-driven / event-driven)
  │
  ├─ 从 data/ 读取历史数据（parquet / csv）
  │
  ├─ 每 tick/event → edge.compute_signals(market_data, external_events)
  │     │
  │     ├─ listing_fade.compute_signals()
  │     ├─ funding_extreme.compute_signals()
  │     ├─ beta_decouple.compute_signals()
  │     ├─ ...（按配置激活）
  │     │
  │     └─ 返回 DataFrame(signal, entry_price, target_price, stop_price, valid_until_ts, meta)
  │
  ├─ ensemble.resolve_conflicts(raw_signals)
  │     └─ 按 priority + (entry_ts, symbol) 去重
  │
  └─ engine 执行订单模拟，调用 metrics 计算指标
```

### 4.2 实盘数据流

```
pipeline.compute_ensemble_signals(inst_ids, equity, risk_guard, strategy_edges)
  │
  ├─ validate_symbols() → 校验 OKX SWAP 存在性
  ├─ fetch_1h_candles(inst_id) × N 个标的（1h kline，96 小时）
  ├─ build_c_market_data() / build_d_market_data() / … × 活跃 edge
  ├─ edge.compute_signals(market_data) × 活跃 edge
  ├─ _compute_signal_score() → 每个信号排序打分
  └─ ensemble.resolve_conflicts() → 输出信号 DataFrame
        │
        ▼
runner.execute_entry_signals()
  ├─ RiskGuard.can_trade() 检查
  ├─ state_machine 检查阶段与冷却
  ├─ okx_client.place_order() 下单
  └─ 持久化 trades.csv / state.json
```

### 4.3 信号输出格式

所有 edge 的 `compute_signals()` 必须返回以下列：

| 字段 | 类型 | 说明 |
|------|------|------|
| `signal` | int | -1/0/+1 |
| `entry_price` | float | 入场价格（post-only limit） |
| `target_price` | float | 止盈目标价 |
| `stop_price` | float | 止损价 |
| `valid_until_ts` | datetime | 信号有效期（时间止损用） |
| `meta` | dict[str, Any] | 序列化的额外元信息 |

### 4.4 信号管道输出格式（pipeline → runner）

| 字段 | 类型 | 说明 |
|------|------|------|
| `symbol` | str | SOL-USDT-SWAP 格式 |
| `edge` | str | "C" / "D" / etc. |
| `signal` | int | 1=long, -1=short |
| `entry_price` | float | 入场价 |
| `direction_label` | str | "long" / "short" |
| `score` | float | z-score 极端度 + R:R 综合评分 |
| `strategy_name` | str | edge 注册名 |
| `entry_ts` | datetime | 信号触发时间 |

---

## 5. Strategy Protocol

所有 edge（A/B/C/D/E/K/H）统一实现 `src/backtest/strategies/base.py` 定义的 `Strategy` protocol：

```python
class Strategy(Protocol):
    config: StrategyConfig

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """返回信号 DataFrame，列定义见 §4.3"""
        ...

    def required_data(self) -> dict[str, list[str]]:
        """{'kline': [...], 'funding': [...], 'events': [...]}"""
        ...
```

`StrategyConfig` 冻结数据类：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | edge 注册名 |
| `leverage_cap` | float | 该 edge 的杠杆上限 |
| `risk_per_trade_R` | float | α/β/γ/δ 阶段的 1R 比例 |
| `universe_fn` | callable | 返回该 edge 的标的列表 |
| `bar_freq` | str | "1m"/"5m"/"1h" |
| `is_event_driven` | bool | True 则由 event_engine 驱动 |

### Edge 注册

```python
STRATEGIES: dict[str, type[Strategy]] = {
    "listing_fade": ListingFadeStrategy,
    "funding_extreme": FundingExtremeStrategy,
    "beta_decouple": BetaDecoupleStrategy,
    "weekend_wick": WeekendWickStrategy,
    "pre_funding_unwind": PreFundingUnwindStrategy,
    "pair_mr": PairMRStrategy,
    "oi_velocity": OIVelocityStrategy,
}
```

---

## 6. 暴击流仓位状态机

### 6.1 4 阶段递进模型

| 阶段 | 权益区间 | 启用 strategy | 单笔 1R 范围 | 杠杆上限 | 心理姿态 |
|------|----------|---------------|-------------|----------|----------|
| **α 破壁** | `$7 ~ $14` | A + E | 18-30% | 10x | 全力击穿翻倍门槛 |
| **β 翻倍** | `$14 ~ $25` | A + B + E + H | 15-20% | 10x | 事件型 + 中频组合 |
| **γ 复利** | `$25 ~ $50` | A + B + C + E + K + H | 15-20% | 8x | 多策略分散 |
| **δ 提现** | `≥ $50` | 全部 | 10% | 5x | 锁收益 |

> 每条 edge 在 α/β 阶段的具体 1R 值由各 edge 设计文档定义，架构层只约定该阶段的范围。

### 6.2 状态转换

```
audit-revision → approved-for-research → paper-live → approved-for-gated-live → halted
```

实现为 `CriticalStrikeStateMachine`：

- `mark_audited()` — 审计通过
- `mark_approved_for_research()` — 批准进入研究
- `mark_paper_live()` — 纸面交易阶段
- `can_enter_live()` → True 时允许实盘
- `can_run_paper()` → True 时允许纸面交易

### 6.3 退场与冷却规则

| 触发 | 行为 |
|------|------|
| 单笔 -1R | 记录 loss，下一信号正常入场 |
| 连续 2 笔 -1R | 冷却 30 分钟 |
| 连续 3 笔 -1R | 冷却 12 小时 + 该 edge 当日停 |
| 单日 DD ≥ 50% | 当日全停 |
| α 阶段权益 < $3 | 整体退场，输出复盘报告 |
| 任一阶段单笔 ≥ +1R | 不补仓不眷恋，目标到即平 |

**严格禁止** add-on（加仓）。暴击流的本意是单笔 R 严格 + 不犹豫退出，加仓违背 R-discipline。

### 6.4 仓位计算公式

```
position_size_usd = (r × V) / |E - S| / E
```

其中：
- `E` = entry price
- `S` = stop price
- `V` = equity
- `r` = 单笔 R%
- 满足 `position_size_usd ≤ V × L`（L = leverage cap），否则降仓至 cap

**1R 校验**：在 stop 价平仓时，权益损失 = `r × V`。

### 6.5 阶段切换条件

- α → β：equity ≥ $14
- β → γ：equity ≥ $25
- γ → δ：equity ≥ $50（一次性提现 $40，留 $10 轻仓继续）
- 回滚：equity 跌回当前阶段下界 80% → 自动回退上一阶段

---

## 7. 全局熔断 (RiskGuard)

`RiskGuard` 是跨所有 edge 共享的运行时熔断器：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `daily_max_drawdown_pct` | 0.15 | 日最大回撤比例 |
| `max_consecutive_losses` | 3 | 连续亏损触发熔断 |
| `max_daily_trades` | 5 | 日交易上限 |

### 7.1 熔断触发路径

```
update_equity(equity, trade_pnl_r)  → 检查三条件（任一满足即 halt）：
  1. current_equity ≤ anchor_equity × (1 - daily_max_drawdown_pct)  →  max_drawdown
  2. consecutive_losses ≥ max_consecutive_losses                      →  consecutive_losses
  3. daily_trades ≥ max_daily_trades                                  →  max_daily_trades

can_trade()  →  return not is_halted
reset_day()  →  重置所有计数器（日切换时调用）
```

### 7.2 熔断与状态机的关系

- `RiskGuard` 是快速熔断（单日/连续亏损），在 `pipeline.compute_ensemble_signals()` 入口检查
- `CriticalStrikeStateMachine` 是慢速状态迁移（阶段切换），在 trade result 确认后触发
- `is_halted == True` 时 pipeline 直接返回空信号，不执行任何 edge

### 7.3 运行前检查

1. `get_account_balance()` 返回 `totalEq >= 7.0`
2. OKX `_flag() == "0"`，打印醒目警告
3. 可交易合约数量 > 0
4. 全局熔断单元测试通过

---

## 8. Ensemble 仲裁层

### 8.1 信号调度

同 bar 或多 edge 同时触发时，由 `EnsembleStrategy.resolve_conflicts()` 处理：

```python
def resolve_conflicts(signals: pd.DataFrame, available_equity: float) -> pd.DataFrame:
    # 1. 按 strategy priority 降序排序
    # 2. 按 (entry_ts, symbol) 分组，每组只保留 priority 最高的信号
    # 3. 返回去重后的信号 DataFrame
```

### 8.2 Priority 表

| edge | priority | 说明 |
|------|----------|------|
| listing_fade | 100 | 事件安全型，优先 |
| funding_extreme | 90 | 中频反转 |
| pre_funding_unwind | 85 | 结算窗反转 |
| beta_decouple | 80 | 中频反转 |
| weekend_wick | 70 | 周末事件 |
| pair_mr | 60 | 低频配对 |
| oi_velocity | 50 | 微观结构型 |

### 8.3 信号质量评分

`pipeline._compute_signal_score()` 在仲裁前对所有信号进行排序评分：

```
score = abs(alt_z) × 10 - sl_distance_pct × 100 + rr_ratio × 5
```

评分维度：
1. z-score 绝对值（越大越极端）
2. 止损距离百分比（越小越好）
3. 风险收益比（TP/SL 距离比）

---

## 9. 持久化与日志

### 9.1 交易流水

运行器将每笔信号与成交记录持久化为 CSV：

```
data/{session}/trades.csv
├── timestamp      : ISO 8601
├── symbol         : SOL-USDT-SWAP
├── action         : enter_long / enter_short / exit_long / exit_short
├── price          : 成交价
├── sz             : 张数
├── pnl            : 已实现盈亏（USDT）
├── pnl_R          : 以 R 计量的盈亏（可选列）
├── reason         : ensemble_signal / take_profit / stop_loss / time_stop
└── metadata       : 关联的 signal 元信息（edge 来源、entry_ts 等）
```

### 9.2 运行状态快照

```
data/{session}/state.json
├── session_start     : ISO 8601
├── cycle_count       : 主循环次数
├── total_trades      : 累计交易笔数
├── peak_equity       : 峰值权益
├── current_equity    : 当前权益
├── current_phase     : α / β / γ / δ
├── halted            : bool
├── halt_reason       : str | null
├── consecutive_losses: int
└── cooldown_until    : ISO 8601 | null
```

### 9.3 缓存数据持久化

| 数据 | 存储路径 | 格式 | 更新频率 |
|------|----------|------|----------|
| OKX 1m kline | `data/okx/kline/{symbol}/{date}.parquet` | parquet | 实时 WS / 回测时一次性下载 |
| OKX 上市公告 | `data/okx/announcements/{date}.json` | JSON | 每 5 分钟轮询 |
| OKX 历史上市事件 | `data/okx/listing_events.csv` | CSV | 一次性 build |
| OKX funding history | `data/okx/funding/{symbol}.parquet` | parquet | 每 8h |
| OKX OI | `data/okx/oi/{symbol}.parquet` | parquet | 每小时或官方最细粒度 |
| OKX leverage cap | `data/okx/leverage/{symbol}.json` | JSON | 上市时实测 |

---

## 10. 外部集成

### 10.1 OKX API 集成架构

```
Runner / Pipeline
  │
  ├─ market_api()  ← 读数据（kline / instruments / tickers）
  ├─ trade_api()   ← 下单（place_order / cancel_order）
  ├─ account_api() ← 账户（get_positions / get_account_balance / set_leverage）
  └─ public_api()  ← 公共（get_instruments）
```

所有 API 调用通过 `python-okx` SDK 封装（`src/okx_sdk.py`），所有外网请求通过本地代理 `http://127.0.0.1:7890`。

### 10.2 订单执行

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 订单类型 | `market` / `post_only limit` | 新 signal 优先 post-only，退出用 market |
| 保证金模式 | `cross` | 全仓，共用账户权益 |
| 持仓模式 | `long_short_mode` | 双向持仓，开仓带 `posSide=long/short` |
| 交易所杠杆 | 合约最大值 | 降低保证金占用，让小资金能开仓 |
| 风险管理 | OKX OCO（`attachAlgoOrds`） | 止盈止损通过 OCO 单管理 |

### 10.3 数据源契约

| 数据 | endpoint | 回测来源 | live 来源 | 必须通过 §18.2 API 签核 |
|------|----------|----------|-----------|----------------------|
| 1m kline | `/market/candles` | 历史下载 | REST + WS subscribe | 否 |
| 上市公告 | `/support/announcements` | 历史 event builder | REST 每 5 分钟 | 否 |
| funding history | `/public/funding-rate-history` | 历史下载 | REST | 否 |
| OI | `/public/open-interest-history` | 历史下载 | REST 每小时 | 是 |
| leverage cap | `/account/max-leverage` | — | REST 上市时实测 | 否 |

**lookahead bias 防护**：所有回测必须模拟 point-in-time 数据发布延迟。未加入延迟建模的回测结果无效。

---

## 11. 风险与约束

### 11.1 架构级风险

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 多 edge 仓位重叠 | 同一 symbol 被多个 edge 同时开仓 | `EnsembleStrategy` 按 `(entry_ts, symbol)` 去重；Runner 检查已有持仓后跳过重复 |
| 两腿 edge 部分成交 | pair MR 只成交一腿，暴露单边 | 3 分钟未成交即平已成交腿，不留单腿暴露 |
| 信号滞后导致入场价偏离 | post-only limit 未成交 | 2 分钟超时放弃，不计为 loss |
| OI 数据 1h 粒度滞后 | H edge 实时判断延迟 | 回测模拟测量延迟，确认胜率不因滞后大幅下降 |
| 强趋势期 funding 不回归 | B/E edge 失效 | 硬止损一刀切；排除时段（CPI/FOMC）规则同样适用 |

### 11.2 不可变更的架构约束

1. **延迟容忍**：所有 edge 的信号尺度必须在 `≥ 1 分钟`，200-400ms 的本地 → 交易所 RTT 不可优化
2. **数据零成本**：不允许新增任何付费数据源。新 edge 必须只用 OKX + Binance 公开免费 API
3. **R-discipline**：单笔 R 严格固定，不允许加仓或马丁格尔
4. **Phase 0 闸门**：任何 edge 进入实盘前必须通过 Phase 0.5 横向验收（样本数、胜率、EV(R)、PF、最大连亏）

### 11.3 排除时段规则（全局适用）

以下时段不允许任何 edge 开仓：

- CPI 公布前后 30 分钟
- FOMC 会议期间
- OKX 系统维护公告窗口
- 账户权益 < $3（整体退场）

---

## 12. 测试契约

### 12.1 单元测试

每个模块必须覆盖：

| 模块 | 测试文件 | 检查点 |
|------|----------|--------|
| 各 edge | `tests/test_<edge>.py` | signal 输出格式、边界条件、空数据处理 |
| ensemble | `tests/test_ensemble.py` | 信号去重、priority 排序、空输入 |
| state_machine | `tests/test_state_machine.py` | 阶段转换、冷却、连续 loss 回滚 |
| risk_guard | `tests/test_risk_guard.py` | 三路熔断触发与 reset |
| pipeline | `tests/test_pipeline.py` | 完整信号链、空数据、API 失败容错 |

### 12.2 集成测试

- 每个 edge 通过 `python -m src.backtest.run --strategy <name>` 产出非零 trades
- `compute_ensemble_signals()` 输出列定义与 runner 的输入契约一致

### 12.3 实盘前校验

1. `$0.5` 名义仓位 echo test 验证下单/撤单/止损/平仓链路
2. 全局熔断单元测试通过
3. state machine 在 paper trading 上 24h 无报错
4. OKX API key 已验证有效 + IP 白名单
5. 监控告警（telegram bot / 邮件）已对接
6. 资金已划入 trading account

---

## 变更历史

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-06-27 | v1 | 初始定稿。从 V3.1 策略计划中提取共享执行架构。包含模块边界、数据流、Strategy protocol、状态机、熔断、仲裁层、持久化、外部集成、风险约束。 |

---

## 相关文档

- [执行计划：V3.1 暴击流组合](../plans/2026-06-25-1500-strategy-v3-zero-data-critical-strike.md) — 执行排期、验收闸门与审计决策
- [Edge 信号设计](../design/2026-06-27-strategy-v3-edge-design.md) — 策略 edge 的信号、阈值与验证规则
- [strategy-and-factor-constraints.md](./strategy-and-factor-constraints.md) — 策略与因子约束吸引子
- [2026-06-26-live-echo-runner.md](../design/2026-06-26-live-echo-runner.md) — C/D ensemble 实盘运行器设计
- [漂移分析报告](../reports/2026-06-27-live-echo-drift-analysis-report.md) — 代码与文档偏差的实际证据
- [okx-sdk-rules.md](./okx-sdk-rules.md) — OKX SDK 使用规范
- [sys-proxy-rules.md](./sys-proxy-rules.md) — 本地代理规范
