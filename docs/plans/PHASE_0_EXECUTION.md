# PHASE 0 EXECUTION SPEC — Liquidation Cascade Fade 回测验证

> **读者**：执行模型（不限智力等级）。**规格作者**：策略设计模型（已锁死）。
> **强制约束**：本文档是唯一真理来源。代码骨架在 `src/backtest/*.py`，需补全 `TODO[cheap-model]` 标记处。**不得修改函数签名、阈值常量、文件路径**。如发现规格与骨架冲突，立即停手并报告，**不得自行决断**。

---

## 0. 角色与边界

### 你（执行模型）只做这 3 件事
1. 按 `任务清单` 顺序执行命令
2. 按代码骨架的 `TODO[cheap-model]` 补全实现
3. 遇到失败：先查 `§7 故障排查表`，仍解决不了 → 输出结构化报告并停手

### 你绝对不做的事
- ❌ 修改任何阈值常量（P95、1.5×ATR、1.2%、0.05% fee 等）
- ❌ 修改函数签名 / 输入输出 schema
- ❌ 修改文件/目录路径
- ❌ "优化" 算法逻辑（除非规格明确要求）
- ❌ 跳过单元测试或验收命令
- ❌ 引入新依赖（requirements.txt 已锁定）
- ❌ 用 mock 数据冒充真实回测结果
- ❌ 在 `print` / `log` 之外的渠道隐藏失败

---

## 1. 验收标准（Decision Gate）

回测完成后，对照下表判定策略命运：

| 主要指标 | 阈值 | 决策 |
|---|---|---|
| 胜率（Win Rate）| ≥ 55% | 进入 Phase 1（实盘聚合器） |
| 胜率 | 50% ~ 55% | 网格搜索阈值，重测一轮 |
| 胜率 | < 50% | 假说证伪，停止 Phase 1，回到策略板 |
| 单笔 EV (in R) | ≥ +0.3R | 必须满足 |
| Profit Factor | ≥ 1.4 | 必须满足 |
| 信号触发频次 | 平均 ≥ 3 笔/天/币种 | 必须满足（太稀疏 → 资金路径不够长） |
| 最大连续亏损笔数 | ≤ 6 | 必须满足（否则破产路径概率超阈） |

**必须三个硬指标全部满足**才能进入 Phase 1。

---

## 2. 最终目录结构（完成状态）

```
okx-bot/
├── .env
├── requirements.txt
├── strategy_plan.md
├── strategy_plan_v2.md
├── PHASE_0_EXECUTION.md          ← 本文档
├── PHASE_0_REPORT.md             ← 你最终输出的报告（T10 生成）
├── src/
│   ├── (旧 main.py / okx_client.py / strategy.py / check_balance.py / test_order.py 保留勿动)
│   └── backtest/
│       ├── __init__.py           ← 已写
│       ├── downloader.py         ← 已写（不要改）
│       ├── loader.py             ← 骨架，需补全
│       ├── features.py           ← 骨架，需补全
│       ├── engine.py             ← 骨架，需补全
│       ├── metrics.py            ← 骨架，需补全
│       ├── run.py                ← 骨架，需补全
│       ├── symbol_universe.json  ← 已写
│       └── tests/
│           ├── fixtures/
│           │   ├── sample_klines.csv      ← 已写
│           │   └── sample_metrics.csv     ← 已写
│           ├── test_loader.py             ← 你写
│           ├── test_features.py           ← 你写
│           └── test_engine.py             ← 你写
├── data/
│   ├── raw/                              ← downloader 产物
│   │   ├── klines_1m/{SYMBOL}/...zip
│   │   ├── metrics/{SYMBOL}/...zip
│   │   └── liquidationSnapshot/{SYMBOL}/...zip
│   └── processed/                        ← loader 落地
│       └── {SYMBOL}_features.parquet
└── reports/
    ├── trades.csv                        ← engine 输出的逐笔交易
    ├── summary.json                      ← metrics 输出
    └── sensitivity_grid.csv              ← 敏感性表
```

---

## 3. 任务清单（严格按顺序）

### T1 ✅ 环境与依赖（已完成）
`requirements.txt` 已更新。无需动作。

### T2 ✅ Downloader（已完成）
`src/backtest/downloader.py` 已写完。不要修改。

### T3 安装依赖 + 冒烟下载
**目的**：验证 venv、proxy、Binance 公网通路。

**命令**（在 `D:\codes\okx-bot\` 下，使用项目内置 venv）：

```bash
./venv/Scripts/python.exe -m pip install -r requirements.txt
./venv/Scripts/python.exe -m src.backtest.downloader \
    --symbols SOLUSDT \
    --start 2026-06-20 \
    --end 2026-06-21 \
    --kinds klines_1m metrics liquidationSnapshot \
    --concurrency 4
```

**验收**：
- 退出码 = 0
- stdout 的 JSON 中 `counts.ok + counts.cached` ≥ 4（klines + metrics 两天，liquidationSnapshot 可 404 不计）
- 文件落地：
  - `data/raw/klines_1m/SOLUSDT/SOLUSDT-klines_1m-2026-06-20.zip`
  - `data/raw/klines_1m/SOLUSDT/SOLUSDT-klines_1m-2026-06-21.zip`
  - `data/raw/metrics/SOLUSDT/SOLUSDT-metrics-2026-06-20.zip`
  - `data/raw/metrics/SOLUSDT/SOLUSDT-metrics-2026-06-21.zip`

**失败 → §7 排查 P1/P2**

### T4 全量数据下载
**目的**：拉齐 25 个候选 symbol × 41 天的 klines + metrics + liquidationSnapshot。

```bash
./venv/Scripts/python.exe -m src.backtest.downloader \
    --symbols $(cat src/backtest/symbol_universe.json | python -c "import json,sys;print(' '.join(json.load(sys.stdin)['candidates']))") \
    --start 2026-05-15 \
    --end 2026-06-24 \
    --kinds klines_1m metrics liquidationSnapshot \
    --concurrency 12
```

> Windows bash 等价命令：`$(...)` 需要 git bash 或 WSL。如不行，直接把候选 symbol 列表手动展开。

**验收**：
- `counts.ok + counts.cached` ≥ `25 * 41 * 2 = 2050`（klines + metrics）
- liquidationSnapshot 的 404 总数允许 ≤ `25 * 41`（即可能全部 404，因 Binance 已下架该 dataset；走 OI 代理路径）
- 写一个文件 `data/raw/_inventory.json`：列出每个 symbol 是否有 klines + metrics 完整 41 天数据。**任何 symbol 缺 > 5 天 → 标记 `excluded: true`，后续 T8 跳过**。

**清单生成命令**（你自己写一个 30 行小脚本 `scripts/build_inventory.py`）。

### T5 loader.py 补全
**目的**：把 raw zip 转成 parquet，统一时间索引（UTC, ms 精度，1-min bar）。

详见 `§5.1 算法规格`。补全后跑：

```bash
./venv/Scripts/python.exe -m src.backtest.tests.test_loader
```

**验收**：所有 `assert` 通过，无 stderr 输出。

### T6 features.py 补全
**目的**：从 parquet 构造 5 个 AND 条件 + 入场方向 + 入场价 + 目标价 + 止损价。

详见 `§5.2 算法规格`。

```bash
./venv/Scripts/python.exe -m src.backtest.tests.test_features
```

**验收**：测试通过 + 对 SOLUSDT 整段时间生成的 features.parquet 行数 = klines 行数 ± 30（容许 NaN warmup 缺失）。

### T7 engine.py 补全
**目的**：事件驱动模拟，输出 trades.csv。

详见 `§5.3 算法规格`。

```bash
./venv/Scripts/python.exe -m src.backtest.tests.test_engine
```

**验收**：fixture 上跑出 exact-match 的 trades（fixture 答案在 `tests/test_engine.py` 内写死）。

### T8 metrics.py + run.py 补全 + 主回测
**目的**：跑全量 + 主报告。

```bash
./venv/Scripts/python.exe -m src.backtest.run \
    --universe src/backtest/symbol_universe.json \
    --start 2026-05-15 \
    --end 2026-06-24 \
    --out reports/
```

**验收**：
- `reports/trades.csv` 存在，> 100 行
- `reports/summary.json` 包含 fields: `win_rate, n_trades, ev_R, profit_factor, max_drawdown_pct, max_consec_losses, trades_per_day_per_symbol`
- 终端打印 `DECISION: PASS|REPARAM|ABORT`

### T9 敏感性扫描
**目的**：在 ±25% 阈值范围内做网格，确认 edge 不是参数过拟合。

```bash
./venv/Scripts/python.exe -m src.backtest.run \
    --universe src/backtest/symbol_universe.json \
    --start 2026-05-15 \
    --end 2026-06-24 \
    --out reports/ \
    --sensitivity
```

详见 `§5.5 敏感性网格`。

**验收**：
- `reports/sensitivity_grid.csv` 存在，包含 ≥ 9 行（3×3 grid 最小）
- 终端打印 grid 表 + `ROBUSTNESS: HIGH|MEDIUM|LOW|FAIL`

### T10 报告生成
**目的**：把所有结果合成 `PHASE_0_REPORT.md`（人类可读 markdown）。

模板见 `§6`。**严禁**虚构数据，所有数字必须来自 `reports/summary.json` 和 `reports/sensitivity_grid.csv`。

---

## 4. 数据 Schema 参考

### 4.1 Binance Futures Klines 1m CSV（无 header）
位置：解压 `{SYMBOL}-klines_1m-{date}.zip` 后的 CSV
列顺序（**严格按此**）：

| idx | name | type | 单位 |
|---|---|---|---|
| 0 | open_time | int64 | ms epoch |
| 1 | open | float | |
| 2 | high | float | |
| 3 | low | float | |
| 4 | close | float | |
| 5 | volume | float | base asset |
| 6 | close_time | int64 | ms epoch |
| 7 | quote_volume | float | USDT |
| 8 | count | int | trade count |
| 9 | taker_buy_volume | float | base asset, **taker BUYS** |
| 10 | taker_buy_quote_volume | float | USDT |
| 11 | ignore | — | 忽略 |

> **注意 Binance 新版 CSV 可能带 header 行**。loader 必须自动检测首行是否为字符串，若是则跳过。

### 4.2 Metrics CSV（5 分钟粒度）
位置：解压 `{SYMBOL}-metrics-{date}.zip` 后的 CSV

| name | type | 含义 |
|---|---|---|
| create_time | str ISO8601 | UTC，5min 边界 |
| symbol | str | |
| sum_open_interest | float | 张数 |
| sum_open_interest_value | float | USDT 名义 |
| count_toptrader_long_short_ratio | float | |
| sum_toptrader_long_short_ratio | float | |
| count_long_short_ratio | float | |
| sum_taker_long_short_vol_ratio | float | |

### 4.3 LiquidationSnapshot CSV（**可能 404**）
| name | type |
|---|---|
| time | int64 ms |
| symbol | str |
| side | "BUY" / "SELL" |
| order_type | str |
| time_in_force | str |
| original_quantity | float |
| price | float |
| average_price | float |
| order_status | str |
| order_last_filled_quantity | float |
| order_filled_accumulated_quantity | float |

> **如果该 dataset 全部 404**：走 OI 代理路径——用 `sum_open_interest_value` 的 5min diff 估算清算 USD 量。详见 §5.2.3。

---

## 5. 算法详细规格

### 5.1 loader.py

**职责**：
- 读取 `data/raw/` 下的所有 zip，解压并解析 CSV
- 统一为 1-minute UTC 时间索引
- metrics 5min → 1min forward-fill
- liquidationSnapshot → 按分钟聚合 USD 量与方向
- 落地 `data/processed/{SYMBOL}_raw.parquet`（**仅 loader 输出，不含 features**）

**函数签名（不许改）**：

```python
def load_klines(symbol: str, start: date, end: date) -> pd.DataFrame
def load_metrics(symbol: str, start: date, end: date) -> pd.DataFrame
def load_liquidations(symbol: str, start: date, end: date) -> pd.DataFrame  # may return empty
def build_raw(symbol: str, start: date, end: date) -> pd.DataFrame  # 合并三者
def cache_raw(symbol: str, start: date, end: date, force: bool = False) -> Path
```

**`build_raw` 输出 schema**（1min 索引）：

| col | dtype | 描述 |
|---|---|---|
| (index) ts | DatetimeIndex UTC | bar open time |
| open, high, low, close | float64 | |
| volume | float64 | base |
| quote_volume | float64 | USDT |
| taker_buy_quote | float64 | USDT, 主动买量 |
| taker_sell_quote | float64 | USDT, 主动卖量 = quote_volume - taker_buy_quote |
| oi_value | float64 | USDT 名义 OI，5min ffill |
| oi_value_diff_5m | float64 | oi_value.diff(5)，正=新增仓位，负=平仓/清算 |
| liq_buy_usd | float64 | 当分钟 BUY 方向清算 USD（无数据时全 NaN） |
| liq_sell_usd | float64 | 当分钟 SELL 方向清算 USD（无数据时全 NaN） |

**关键算法**：
- 时间对齐：用 `pd.date_range(start, end, freq='1min')` 作为 master index
- metrics 的 5min ffill：`metrics_5m.reindex(master_index).ffill(limit=5)`
- liquidations 聚合：`df.groupby([pd.Grouper(key='time', freq='1min'), 'side']).agg(usd=('usd','sum')).unstack()`
- 缺数据填充：klines 缺一两个分钟 → `ffill(limit=2)`；缺超过 2 分钟 → 抛 `ValueError`

### 5.2 features.py

**职责**：基于 `build_raw` 输出，计算所有 entry 条件 + 信号方向 + 价位。

**函数签名**：

```python
def compute_features(raw: pd.DataFrame, params: FeatureParams) -> pd.DataFrame
```

**FeatureParams（dataclass，默认值锁死，不许改）**：

```python
@dataclass(frozen=True)
class FeatureParams:
    vwap_window_min: int = 15
    atr_window_min: int = 15
    liq_rolling_sec: int = 60          # 60s rolling 清算 USD
    liq_p_quantile: float = 0.95       # P95
    liq_lookback_hours: int = 24       # rolling 窗口
    single_side_threshold: float = 0.80
    displacement_min_atr: float = 1.5
    warmup_min_bars: int = 24 * 60     # 24h warmup
```

**输出 schema（在 raw 基础上追加）**：

| col | dtype | 描述 |
|---|---|---|
| vwap_15m | float64 | rolling 15min volume-weighted avg price |
| atr_15m | float64 | rolling 15min ATR (Wilder) |
| displacement | float64 | (close - vwap_15m) / atr_15m |
| flow_imbalance | float64 | (taker_buy_quote - taker_sell_quote) / quote_volume，roll(60s).mean() |
| single_side_ratio | float64 | abs(flow_imbalance)，[0..1] |
| liq_usd_60s | float64 | rolling 60s 总清算 USD（或 OI 代理） |
| liq_p95 | float64 | rolling 24h 的 liq_usd_60s P95 |
| liq_accel | float64 | liq_usd_60s 的 2nd derivative（差分两次） |
| cond_volume | bool | liq_usd_60s > liq_p95 |
| cond_single_side | bool | single_side_ratio > 0.80 |
| cond_displacement | bool | abs(displacement) > 1.5 |
| cond_decelerating | bool | liq_accel < 0 |
| signal | int | 0=无信号; +1=做多(fade down spike); -1=做空(fade up spike) |
| entry_price | float | 下一根 1m bar 的 open（lookahead-safe） |
| target_price | float | 0.5*(entry + vwap_at_entry) |
| stop_price | float | entry * (1 - 0.012*sign(signal))，逆向 1.2% |

**信号生成规则（精确）**：

```
all_cond = cond_volume AND cond_single_side AND cond_displacement AND cond_decelerating
if all_cond:
    if displacement < -displacement_min_atr AND flow_imbalance < 0:
        signal = +1   # 多头方向（fade sell cascade）
    elif displacement > +displacement_min_atr AND flow_imbalance > 0:
        signal = -1   # 空头方向（fade buy cascade）
    else:
        signal = 0    # displacement 与 flow 不一致，不交易
else:
    signal = 0
```

**lookahead 防护**：
- `entry_price = open[t+1]`（注意：必须 shift，**不许用 t 时的 close 当 entry**）
- `target_price` / `stop_price` 在 t+1 entry 时锁定，使用 t 时的 vwap_at_t

#### 5.2.3 OI 代理路径（liquidationSnapshot 全部 404 时启用）

如果 raw DataFrame 中 `liq_buy_usd` 和 `liq_sell_usd` 全为 NaN：

```
oi_drop = (-oi_value_diff_5m).clip(lower=0)        # 只取下降部分
oi_drop_per_min = oi_drop / 5                       # 5min diff 平摊到 1min
liq_usd_60s_proxy = oi_drop_per_min.rolling(60, min_periods=10).sum()
# 方向用 flow_imbalance 推断：flow < 0 → sell-side liquidation; flow > 0 → buy-side
```

> 这是次优代理，需在 PHASE_0_REPORT.md 中**显著标注**结果是用代理算的。

### 5.3 engine.py

**职责**：从 features.parquet 模拟逐笔交易，输出 trades.

**函数签名**：

```python
def simulate(features: pd.DataFrame, params: ExecParams) -> pd.DataFrame
```

**ExecParams（默认锁死）**：

```python
@dataclass(frozen=True)
class ExecParams:
    fee_taker_per_side: float = 0.0005       # 0.05% OKX taker
    slippage_per_side: float = 0.0003        # 0.03% per side
    time_stop_bars: int = 2                  # 2 × 1min = 120s ≈ 90s 设计目标
    risk_per_trade_pct: float = 0.20         # 20% equity per trade
    leverage: float = 12.0                   # 仓位/权益 = 12x
    initial_equity: float = 7.0
    cooldown_after_loss_bars: int = 30       # 连亏 2 笔后冷却 30 bars
    daily_max_drawdown_pct: float = 0.45     # 日内 -45% 停手
```

**状态机**：

```
state = "FLAT"
equity = initial_equity
recent_losses = deque(maxlen=2)
cooldown_until = None
daily_anchor_equity = equity
daily_anchor_date = first_date

for ts, row in features.iterrows():
    # 1. 每日 anchor 更新与日内 DD 检查
    if ts.date() != daily_anchor_date:
        daily_anchor_equity = equity
        daily_anchor_date = ts.date()
    if equity < daily_anchor_equity * (1 - daily_max_drawdown_pct):
        state = "HALTED_TODAY"  # 当日不再开新仓
    
    # 2. 冷却检查
    if cooldown_until and ts < cooldown_until:
        skip new entries
    
    # 3. 状态转移
    if state == "FLAT" and row.signal != 0 and not HALTED_TODAY:
        entry_ts = ts (next bar already factored in entry_price)
        entry_bar_idx = current
        state = "IN_TRADE"
        ... record entry
    elif state == "IN_TRADE":
        # check exits in this bar:
        # - 时间止损：bar_idx - entry_bar_idx >= time_stop_bars → exit at this bar's close
        # - 止损：bar.high/low 触及 stop_price → exit at stop_price (pessimistic if both hit)
        # - 止盈：bar.high/low 触及 target_price → exit at target_price
        # 若同 bar 内 SL 和 TP 都触发 → 假定 SL 先（保守）
        ... record exit, compute pnl_R, update equity, append to recent_losses
        state = "FLAT"
        if all(recent_losses are losses) and len(recent_losses)==2:
            cooldown_until = ts + 30 * 1min
```

**pnl 计算**（关键，不许错）：

```python
# 名义仓位
notional = equity * risk_per_trade_pct * leverage / abs(stop_distance_pct)
# 但更直接：固定 risk_per_trade_pct 权益对应 1R 损失
# 1R = risk_per_trade_pct * equity（损失上限）
# 所以 position_size 满足: |entry_price - stop_price| / entry_price * leverage * equity_used == risk_per_trade_pct * equity
# 简化：直接用 R 单位记账

entry_fill = entry_price * (1 + slippage_per_side * sign)        # 不利方向
exit_fill = exit_price * (1 - slippage_per_side * sign)          # 不利方向

# raw pct return on the underlying (signed by direction)
raw_ret = sign * (exit_fill - entry_fill) / entry_fill
# 减去双边手续费
net_ret = raw_ret - 2 * fee_taker_per_side
# R 倍数：把 stop_distance 当作 1R
stop_distance_pct = 0.012   # 来自规格
pnl_R = net_ret / stop_distance_pct
# 权益更新（含杠杆，但因 1R = 20% equity，直接：）
equity_change = equity * risk_per_trade_pct * pnl_R
equity += equity_change
```

> **校验**：1R 完全亏损时 `equity_change == -0.20 * equity`。若你写完后这个不等式不成立，**回头检查**。

**trades.csv 输出列**：

```
entry_ts, exit_ts, symbol, side ("LONG"/"SHORT"),
entry_price, exit_price, target_price, stop_price,
exit_reason ("TP"/"SL"/"TIME"),
pnl_R, pnl_pct_equity, equity_after
```

### 5.4 metrics.py

**输出 `summary.json`**：

```json
{
  "n_trades": int,
  "win_rate": float (0..1),
  "ev_R": float,
  "profit_factor": float,
  "max_drawdown_pct": float,
  "max_consec_losses": int,
  "max_consec_wins": int,
  "trades_per_day_per_symbol": float,
  "avg_holding_bars": float,
  "best_trade_R": float,
  "worst_trade_R": float,
  "by_symbol": {symbol: {n, wr, ev_R}},
  "by_hour_utc": {hour: {n, wr, ev_R}},
  "exit_reason_breakdown": {"TP": n, "SL": n, "TIME": n},
  "decision": "PASS" | "REPARAM" | "ABORT"
}
```

**decision 判定**（必须按此实现，不许改）：

```python
if win_rate >= 0.55 and ev_R >= 0.3 and profit_factor >= 1.4 \
   and trades_per_day_per_symbol >= 3 and max_consec_losses <= 6:
    decision = "PASS"
elif 0.50 <= win_rate < 0.55:
    decision = "REPARAM"
else:
    decision = "ABORT"
```

### 5.5 敏感性网格

**默认扫描 3 个维度的 ±25%**：

| 参数 | 中值 | 低值 | 高值 |
|---|---|---|---|
| liq_p_quantile | 0.95 | 0.90 | 0.99 |
| displacement_min_atr | 1.5 | 1.0 | 2.0 |
| time_stop_bars | 2 | 1 | 4 |

3×3×3 = 27 cells. 对每个 cell 跑全量回测，记 `win_rate, ev_R, n_trades`。

**ROBUSTNESS 判定**：
- HIGH：27 cells 中 ≥ 22 cell PASS
- MEDIUM：14-21 cell PASS
- LOW：5-13 cell PASS
- FAIL：< 5 cell PASS

只要 ROBUSTNESS ≤ LOW → 即使主回测 PASS 也判为 REPARAM。

---

## 6. PHASE_0_REPORT.md 报告模板

T10 输出，**严格按此结构**，所有数字从 summary.json / sensitivity_grid.csv 抽取，**不许虚构**：

```markdown
# Phase 0 回测报告 — Liquidation Cascade Fade

## 1. 数据集
- 时间窗口: {start} ~ {end}（{n_days} 天）
- Symbol 数: {n_symbols} （已排除 {excluded_symbols}）
- 总 bar 数: {total_bars}
- 清算数据来源: {"liquidationSnapshot 实数据" | "OI 代理"}  ← 必须如实标注

## 2. 主回测结果
| 指标 | 值 | 阈值 | 通过? |
|---|---|---|---|
| 胜率 | {win_rate} | ≥ 55% | ✓/✗ |
| EV (R) | {ev_R} | ≥ +0.3 | ✓/✗ |
| Profit Factor | {pf} | ≥ 1.4 | ✓/✗ |
| 信号频次 | {tps} 笔/天/币 | ≥ 3 | ✓/✗ |
| 最大连亏 | {mcl} | ≤ 6 | ✓/✗ |
| **DECISION** | **{decision}** | | |

## 3. 按 symbol 分组
（贴 by_symbol 表格）

## 4. 按 UTC 小时分组
（贴 by_hour 表格 + 1 行结论：哪些时段最好/最差）

## 5. 出场原因分布
（TP/SL/TIME 各占比）

## 6. 敏感性
（贴 27 cells 网格摘要 + ROBUSTNESS 判定）

## 7. 资金曲线
（如果实现了 equity_curve.png 就贴；否则贴起止权益与 max DD）

## 8. 结论与建议
基于上面数据，下一步行动：
- 如果 PASS + HIGH ROBUSTNESS → 进入 Phase 1
- 如果 REPARAM → 列出网格中最佳 cell 的参数，建议重测
- 如果 ABORT → 列出失败的主要原因（胜率不足？信号太稀？连亏过长？）

## 9. 已知局限
- 数据源是 Binance，OKX 实盘可能存在 5-15% 行为偏差
- 滑点估算为 0.03% per side，极端清算时段可能更高
- 未模拟 funding rate 切换、未模拟交易所网络抖动
```

---

## 7. 故障排查表

| ID | 症状 | 原因 | 修复 |
|---|---|---|---|
| P1 | downloader 全部超时 | proxy 不通 | `curl -x http://127.0.0.1:7890 https://data.binance.vision` 测；改 `.env` 的 `HTTP_PROXY` |
| P2 | downloader 全部 403 | Binance 公网 IP 被限速 | 加 `--concurrency 2`，重试；或切代理出口 |
| P3 | klines CSV 解析为空 | Binance 改成带 header 了 | loader 必须自动检测首行：try parse float on col 0; 如失败则跳过首行 |
| P4 | metrics 缺失某天 | 个别 symbol 在某日 listing 前 | loader 直接 ffill；如缺超过 5 天 → 该 symbol 移出 universe |
| P5 | liquidationSnapshot 全 404 | dataset 已下架 | 启用 §5.2.3 OI 代理路径，并在报告中标注 |
| P6 | features 输出全 NaN | warmup 24h 未到 | 检查数据起始日是否扣掉了 warmup；预留 1 天 buffer |
| P7 | simulate 抛 KeyError "signal" | features 没正确生成 signal 列 | 回头检查 §5.2 的信号生成代码块 |
| P8 | pnl_R 数量级离谱（>100 或 <-100） | equity 更新公式错 | 用 §5.3 末尾的校验式自检 |
| P9 | trades.csv < 10 行 | 信号阈值过严 OR warmup 太长 OR 数据太少 | 检查 cond_* 每个的 True 占比 |
| P10 | UnicodeDecodeError 解 zip | zip 内有 macOS metadata | 用 `zipfile.ZipFile` 过滤掉以 `__MACOSX/` 开头的成员 |

---

## 8. 禁止事项（违反 = 任务失败）

- ❌ 不准让 LLM 帮你"猜测"数据。一切数字必须来自实际跑出的 csv/json。
- ❌ 不准在 simulate 内使用未来 bar 数据（lookahead bias）。
- ❌ 不准用 mock 数据冒充全量回测。
- ❌ 不准跳过失败的 symbol 而不在 `_inventory.json` 记录。
- ❌ 不准修改 `FeatureParams` / `ExecParams` 默认值（敏感性扫描通过函数参数覆盖，不改默认）。
- ❌ 不准在 trades.csv 里写 NaN pnl。
- ❌ 不准擅自把 leverage 调到 20-30x；本回测固定 12x。

---

## 9. 完成判定（你回报给规格作者的内容）

完成时输出：

```
[PHASE 0 COMPLETE]
- T3 smoke download:        OK
- T4 full download:         OK (X symbols × 41 days, Y cells, Z 404)
- T5 loader:                OK (all tests pass)
- T6 features:              OK (all tests pass)
- T7 engine:                OK (all tests pass)
- T8 main backtest:         OK / FAIL (DECISION: PASS|REPARAM|ABORT)
- T9 sensitivity:           OK / FAIL (ROBUSTNESS: HIGH|MEDIUM|LOW|FAIL)
- T10 report:               PHASE_0_REPORT.md generated
- Liquidation data source:  REAL / OI_PROXY
- Total runtime:            X min
- Outstanding issues:       (列表 or "无")
```

如果任何一步失败：

```
[PHASE 0 BLOCKED]
- Failed at: T_X
- Symptom: ...
- Tried: ...
- Need decision on: ...  ← 必须问，不许擅自决断
```

---

## 10. 给执行者的最后忠告

1. **逐步执行**：T3 不通过就不要碰 T4。
2. **每个 T 完成后**：把验收输出（命令的 stdout + 关键文件 ls）粘贴出来。
3. **遇到歧义**：停手，看 §7；§7 没覆盖 → 报 BLOCKED。
4. **不要美化数据**：胜率 47% 就写 47%，不要凑到 50%。
5. **不要并发执行 T**：依赖关系是严格线性的。
