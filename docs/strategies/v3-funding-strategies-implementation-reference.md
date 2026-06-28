# V3 Funding 策略实现参考 —— Edge B / Edge E 代码解剖

> **用途：** 为 Alpha（funding regime switch）与 Gamma（settlement compression）策略提供可直接复用的实现模板。
> **来源：** `src/backtest/strategies/funding_extreme.py`（Edge B）、`src/backtest/strategies/pre_funding_unwind.py`（Edge E）
> **更新日期：** 2026-06-28

---

## 1. 整体架构契约

### 1.1 策略类必须实现的接口

所有 V3 策略继承自同一个 `Strategy` Protocol，位于 `src/backtest/strategies/base.py`：

```python
# base.py:23-34
class Strategy(Protocol):
    config: StrategyConfig

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        ...

    def required_data(self) -> dict[str, list[str]]:
        ...
```

**关键约束：**
- `config` 必须是类属性（非实例属性），供 runner 在初始化时读取
- `compute_signals` 接收单 symbol 的 `market_data`（index 为 Timestamp），返回信号 DataFrame
- `external_events` 仅在 event-driven 策略中使用（如 listing_fade）

### 1.2 策略配置结构

```python
# base.py:12-20
@dataclass(frozen=True)
class StrategyConfig:
    name: str
    leverage_cap: float
    risk_per_trade_R: float
    universe_fn: UniverseFn
    bar_freq: str
    is_event_driven: bool
    metadata: dict[str, Any] = field(default_factory=dict)
```

**Edge B 与 Edge E 的配置对比：**

| 字段 | Edge B (`funding_extreme`) | Edge E (`pre_funding_unwind`) |
|------|---------------------------|------------------------------|
| `name` | `"funding_extreme"` | `"pre_funding_unwind"` |
| `leverage_cap` | `8.0` | `8.0` |
| `risk_per_trade_R` | `0.20` | `0.18` |
| `bar_freq` | `"1h"` | `"10m"` |
| `is_event_driven` | `False` | `False` |
| `metadata` | `{"edge": "B"}` | `{"edge": "E"}` |

> **模板要点：** Alpha/Gamma 策略应直接复用此 `StrategyConfig` 结构，仅需调整 `bar_freq` 与 `risk_per_trade_R`。

---

## 2. 数据需求声明

### 2.1 `required_data()` 方法

策略通过此方法声明所需数据字段，runner 在加载时会据此合并数据：

**Edge B（`funding_extreme.py:19-24`）：**
```python
def required_data(self) -> dict[str, list[str]]:
    return {
        "kline": ["close", "high", "low", "quote_volume"],
        "funding": ["funding_rate"],
        "oi": ["oi_value"],
    }
```

**Edge E（`pre_funding_unwind.py:19-24`）：**
```python
def required_data(self) -> dict[str, list[str]]:
    return {
        "kline": ["close", "high", "low", "quote_volume"],
        "funding": ["funding_rate", "next_funding_time"],
        "oi": ["oi_value"],
    }
```

**关键差异：**
- Edge E 额外需要 `next_funding_time`，用于计算距结算的时间窗口
- Edge B 仅依赖 `funding_rate` 的时序统计量

> **模板要点：** Alpha（regime switch）可能需 funding 历史 + 波动率；Gamma（settlement compression）必须需要 `next_funding_time`（同 Edge E）。

### 2.2 数据加载与合并流程

Runner 在 `run.py:80-120` 中统一处理数据加载：

```python
# run.py:80-98
def _load_okx_funding(frame: pd.DataFrame, inst_id: str) -> None:
    """Try loading OKX funding rate; silently skip if unavailable."""
    try:
        funding = fetch_funding_history(inst_id, limit=200)
        if not funding.empty and "funding_time" in funding.columns and "funding_rate" in funding.columns:
            funding = funding.rename(columns={"funding_time": "ts"}).set_index("ts")
            funding.index = pd.to_datetime(funding.index, utc=True)
            frame.index = pd.to_datetime(frame.index, utc=True)
            frame["funding_rate"] = funding["funding_rate"].reindex(frame.index, method="ffill", limit=500).values
            frame["next_funding_time"] = funding.index[0]
            return
    except Exception:
        pass
    # Fallback: proxy funding rate from 1h price return
    returns = frame["close"].pct_change(60, fill_method=None)
    roll_std = returns.rolling(288, min_periods=20).std().fillna(0.001)
    frame["funding_rate"] = (returns.clip(-0.05, 0.05) * 0.1 / roll_std.replace(0, 0.001)).fillna(0.0)
    frame["next_funding_time"] = pd.NaT
```

**数据流：**
1. K 线数据优先从 Binance 缓存加载（`cache_raw`），回退到 OKX
2. Funding 数据通过 `fetch_funding_history()` 从 OKX API 获取
3. OI 数据若不在 Binance parquet 中，则填充 `np.nan`
4. 所有数据合并为单 DataFrame，index 对齐为 UTC Timestamp

> **模板要点：** Alpha/Gamma 策略无需改动数据加载层，只需在 `required_data()` 中声明字段即可。

---

## 3. 信号生成逻辑

### 3.1 共同框架

两个策略共享同一信号生成框架（`funding_extreme.py:26-78` / `pre_funding_unwind.py:26-88`）：

```python
def compute_signals(self, market_data: pd.DataFrame, external_events=None) -> pd.DataFrame:
    if market_data.empty or len(market_data) < 5:
        return pd.DataFrame()

    frame = market_data.copy()
    # ... 计算指标 ...

    signals: list[dict[str, object]] = []
    for idx in range(5, len(frame)):
        row = frame.iloc[idx]
        # ... 过滤条件 ...

        direction = -1 if float(funding_z) > 0 else 1
        entry_price = float(row["close"])
        stop_distance = max(float(row["high"] - row["low"]), entry_price * 0.015)  # Edge B
        stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
        target_price = entry_price - stop_distance if direction < 0 else entry_price + stop_distance
        valid_until_ts = frame.index[min(idx + 3, len(frame) - 1)]  # Edge B
        signals.append({
            "entry_ts": frame.index[idx],
            "valid_until_ts": valid_until_ts,
            "signal": direction,
            "entry_price": entry_price,
            "target_price": target_price,
            "stop_price": stop_price,
        })

    return pd.DataFrame(signals)
```

**信号 DataFrame 输出列：**

| 列名 | 类型 | 含义 |
|------|------|------|
| `entry_ts` | Timestamp | 信号生成时间 |
| `valid_until_ts` | Timestamp | 信号有效期截止（时间止损） |
| `signal` | int | `+1` = LONG, `-1` = SHORT |
| `entry_price` | float | 入场价（当前 bar close） |
| `target_price` | float | 止盈价 |
| `stop_price` | float | 止损价 |

### 3.2 Edge B：Funding Extreme（`funding_extreme.py`）

**核心逻辑：** 当 funding rate 偏离近期均值超过 2σ，且 OI 处于高位时，反向开仓（fade the funding）。

**指标计算（`funding_extreme.py:35-41`）：**
```python
funding_history = frame["funding_rate"].shift(1)
frame["funding_mean"] = funding_history.rolling(5, min_periods=5).mean()
frame["funding_std"] = funding_history.rolling(5, min_periods=5).std(ddof=0)
frame["funding_z"] = (frame["funding_rate"] - frame["funding_mean"]) / frame["funding_std"].replace(0, pd.NA)
frame["oi_ratio"] = frame["oi_value"] / frame["quote_volume"].replace(0, pd.NA)
frame["oi_threshold"] = frame["oi_ratio"].shift(1).rolling(5, min_periods=5).quantile(0.8)
frame["price_1h_return"] = frame["close"].pct_change()
```

**入场过滤（`funding_extreme.py:51-60`）：**
```python
if abs(float(funding_z)) < 2.0:           # 过滤：|z-score| >= 2
    continue
if float(oi_ratio) <= float(oi_threshold):  # 过滤：OI ratio 必须高于 80% 分位
    continue
if float(funding_z) > 0 and float(price_ret) >= 0:  # 过滤：正 funding 时价格必须下跌
    continue
if float(funding_z) < 0 and float(price_ret) <= 0:  # 过滤：负 funding 时价格必须上涨
    continue
```

**风控参数：**
- Stop distance：`max(high - low, close * 0.015)`（`funding_extreme.py:64`）
- Time stop：`valid_until = entry_ts + 3 bars`（即 3 小时，因 bar_freq=1h）

### 3.3 Edge E：Pre-Funding Unwind（`pre_funding_unwind.py`）

**核心逻辑：** 在 funding 结算前 5~60 分钟，若 funding rate 极端且 OI 加速堆积，则反向开仓，预期结算后仓位 unwind。

**指标计算（`pre_funding_unwind.py:35-44`）：**
```python
funding_history = frame["funding_rate"].shift(1)
frame["funding_mean"] = funding_history.rolling(100, min_periods=50).mean()
frame["funding_std"] = funding_history.rolling(100, min_periods=50).std(ddof=0)
frame["funding_z"] = (frame["funding_rate"] - frame["funding_mean"]) / frame["funding_std"].replace(0, pd.NA)
frame["oi_ratio"] = frame["oi_value"] / frame["quote_volume"].replace(0, pd.NA)
oi_history = frame["oi_ratio"].shift(1)
frame["oi_mean"] = oi_history.rolling(5, min_periods=5).mean()
frame["oi_std"] = oi_history.rolling(5, min_periods=5).std(ddof=0)
frame["oi_z"] = (frame["oi_ratio"] - frame["oi_mean"]) / frame["oi_std"].replace(0, pd.NA)
frame["price_delta"] = frame["close"] - frame["close"].shift(3)
```

**关键差异 vs Edge B：**
- Funding 滚动窗口：`100` bars（vs Edge B 的 `5`），对应约 16 小时历史（bar_freq=10m）
- OI 使用 z-score 而非绝对阈值：`oi_z` 衡量 OI 的近期异常度
- 引入 `price_delta`（3 bar 价格变化）作为价格确认

**时间窗口过滤（`pre_funding_unwind.py:49-56`）：**
```python
funding_time = row.get("next_funding_time")
if pd.isna(funding_time):
    continue

now = frame.index[idx]
minutes_to_settlement = (pd.Timestamp(funding_time) - now).total_seconds() / 60.0
if minutes_to_settlement < 5 or minutes_to_settlement > 60:
    continue
```

**入场过滤（`pre_funding_unwind.py:58-70`）：**
```python
if abs(float(funding_z)) < 1.8:           # 过滤：|z-score| >= 1.8（比 Edge B 更宽松）
    continue
if float(oi_z) < 1.0:                     # 过滤：OI z-score >= 1
    continue
if float(funding_z) > 0 and float(price_delta) >= 0:  # 过滤：正 funding 时价格必须下跌
    continue
if float(funding_z) < 0 and float(price_delta) <= 0:  # 过滤：负 funding 时价格必须上涨
    continue
```

**风控参数：**
- Stop distance：`max(high - low, close * 0.01)`（`pre_funding_unwind.py:74`）—— 比 Edge B 更紧
- Time stop：`valid_until = funding_time + 30 minutes`（`pre_funding_unwind.py:77`）

### 3.4 信号生成对比表

| 维度 | Edge B | Edge E |
|------|--------|--------|
| **触发条件** | Funding z-score >= 2.0 | Funding z-score >= 1.8 |
| **OI 确认** | OI ratio > 80% 分位（5 bar） | OI z-score > 1.0（5 bar） |
| **价格确认** | 当前 bar return 与 funding 反向 | 3 bar delta 与 funding 反向 |
| **时间约束** | 无 | 结算前 5~60 分钟 |
| **止损距离** | `max(range, 1.5%)` | `max(range, 1.0%)` |
| **时间止损** | 3 bars（3 小时） | 结算后 30 分钟 |
| **方向逻辑** | Fade funding（正 funding → Short） | Fade funding（正 funding → Short） |

> **模板要点：**
> - Alpha（regime switch）可参考 Edge B 的 z-score 阈值 + OI 确认结构
> - Gamma（settlement compression）应直接复用 Edge E 的 `next_funding_time` 时间窗口机制

---

## 4. 止损与止盈计算模式

两个策略使用完全相同的 stop/target 计算模式（基于 bar range 的固定比例混合）：

```python
# 通用模板（Edge B:64-66, Edge E:74-76）
stop_distance = max(float(row["high"] - row["low"]), entry_price * X)
stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
target_price = entry_price - stop_distance if direction < 0 else entry_price + stop_distance
```

**参数对比：**

| 策略 | `X`（最小 stop 比例） | 隐含 R:R |
|------|----------------------|----------|
| Edge B | `0.015`（1.5%） | 1:1（target = entry ± 1R） |
| Edge E | `0.01`（1.0%） | 1:1（target = entry ± 1R） |

> **注意：** 两个策略的 target 都是对称的 1R，即止盈 = 入场价 ± stop_distance。这意味着它们都是 1:1 盈亏比策略，依赖高胜率盈利。

---

## 5. 回测引擎中的 R-基于仓位管理

### 5.1 回测引擎执行参数

`src/backtest/engine.py:15-24`：

```python
@dataclass(frozen=True)
class ExecParams:
    fee_taker_per_side: float = 0.0005    # 0.05% 单边
    slippage_per_side: float = 0.0003     # 0.03% 单边
    time_stop_bars: int = 2               # 仅用于 Phase 0 legacy 流程
    risk_per_trade_pct: float = 0.20      # 账户的 20% 作为 1R
    leverage: float = 12.0                # 最大杠杆
    initial_equity: float = 7.0           # 初始资金（单位：k USDT）
    cooldown_after_loss_bars: int = 30    # 2 连亏后冷却 30 bar
    daily_max_drawdown_pct: float = 0.45  # 日最大回撤 45%
```

> **重要：** `ExecParams.risk_per_trade_pct`（0.20）与策略的 `StrategyConfig.risk_per_trade_R`（Edge B: 0.20, Edge E: 0.18）是不同概念：
> - `ExecParams.risk_per_trade_pct`：回测引擎中每笔交易承担账户百分之几的风险
> - `StrategyConfig.risk_per_trade_R`：策略声明的 R 值，供 live runner 计算仓位

### 5.2 PnL 计算逻辑

`engine.py:124-132`：

```python
sign = float(entry_signal)
entry_fill = entry_price * (1.0 + params.slippage_per_side * sign)
exit_fill = exit_px * (1.0 - params.slippage_per_side * sign)
raw_ret = sign * (exit_fill - entry_fill) / entry_fill
net_ret = raw_ret - 2.0 * params.fee_taker_per_side
pnl_R = net_ret / stop_distance_pct                    # 归一化为 R
equity_change = equity * params.risk_per_trade_pct * pnl_R
```

**仓位公式推导：**
- `risk_per_trade_pct = 0.20`（账户的 20%）
- `stop_distance_pct = 0.012`（固定 1.2%）
- 仓位大小 = `risk_amount / (stop_distance * leverage)` = `equity * 0.20 / (0.012 * 12)` ≈ `equity * 1.39`

### 5.3 Named Strategy 回测路径

对于 V3 策略（非 Phase 0 legacy），`run.py:193-246` 提供了简化回测路径：

```python
def run_named_strategy(strategy_name, start, end, universe_path, out_dir):
    strategy = load_strategy(strategy_name)
    # ... 加载数据 ...
    signals = strategy.compute_signals(market_data)
    # ... 转换为 trades DataFrame ...
    trades["pnl_R"] = raw_ret / stop_distance_pct.replace(0, pd.NA)
```

> **模板要点：** Alpha/Gamma 策略可直接复用 `run_named_strategy()` 路径，无需改动 engine。

---

## 6. 策略注册表

### 6.1 注册方式

`src/backtest/strategies/__init__.py:14-23`：

```python
STRATEGIES = {
    "listing_fade": ListingFadeStrategy,
    "funding_extreme": FundingExtremeStrategy,
    "ensemble": EnsembleStrategy,
    "pre_funding_unwind": PreFundingUnwindStrategy,
    "beta_decouple": BetaDecoupleStrategy,
    "weekend_wick": WeekendWickStrategy,
    "pair_mr": PairMRStrategy,
    "oi_velocity": OIVelocityStrategy,
}
```

### 6.2 Runner 加载流程

`run.py:43-48`：

```python
def load_strategy(name: str):
    strategy_cls = STRATEGIES.get(name)
    if strategy_cls is None:
        raise ValueError(f"Unknown strategy: {name}")
    return strategy_cls()
```

> **模板要点：** Alpha/Gamma 策略实现后，必须在 `__init__.py` 的 `STRATEGIES` dict 中注册，才能通过 `run.py --strategy <name>` 调用。

---

## 7. 测试模式

### 7.1 Edge B 测试（`test_funding_extreme_strategy.py:6-27`）

```python
def test_funding_extreme_fades_positive_extreme_with_oi_confirmation():
    index = pd.date_range("2026-06-25 00:00:00", periods=6, freq="1h", tz="UTC")
    market_data = pd.DataFrame({
        "close": [100, 101, 102, 101, 100.5, 100],
        "high": [101, 102, 103, 102, 101, 100.5],
        "low": [99, 100, 101, 100, 99.5, 99],
        "funding_rate": [0.001, 0.002, 0.003, 0.004, 0.02, 0.05],  # 最后两期极端
        "oi_value": [1000, 1010, 1020, 1100, 1400, 1500],          # OI 递增
        "quote_volume": [10000, 10000, 10000, 10000, 10000, 10000],
    }, index=index)

    strategy = FundingExtremeStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    last_signal = signals.iloc[-1]
    assert last_signal["signal"] == -1        # 正 funding → Short
    assert last_signal["entry_price"] == market_data.iloc[-1]["close"]
    assert last_signal["stop_price"] > last_signal["entry_price"]
```

### 7.2 Edge E 测试（`test_pre_funding_unwind_strategy.py:6-35`）

```python
def test_pre_funding_unwind_requires_settlement_window_and_reversal():
    index = pd.date_range("2026-06-25 07:00:00", periods=7, freq="10min", tz="UTC")
    market_data = pd.DataFrame({
        "close": [100, 102, 104, 105, 104, 103, 102],
        "high": [101, 103, 105, 106, 105, 104, 103],
        "low": [99, 101, 103, 104, 103, 102, 101],
        "funding_rate": [0.001, 0.002, 0.004, 0.01, 0.012, 0.03, 0.014],
        "oi_value": [1000, 1100, 1250, 1400, 1500, 1600, 1700],
        "quote_volume": [10000, 10000, 10000, 10000, 10000, 10000, 10000],
        "next_funding_time": [
            pd.Timestamp("2026-06-25 08:00:00Z"),  # 结算时间固定
            # ... 重复 6 次 ...
            pd.Timestamp("2026-06-25 16:00:00Z"),  # 最后一期超出窗口
        ],
    }, index=index)

    strategy = PreFundingUnwindStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    signal = signals.iloc[-1]
    assert signal["signal"] == -1
    assert signal["valid_until_ts"] >= signal["entry_ts"]
```

> **模板要点：** Alpha/Gamma 策略应提供类似的单元测试，验证：
> 1. 信号方向与 funding 极性相反
> 2. 时间窗口约束生效（对 Gamma）
> 3. OI/波动率确认条件过滤无效信号

---

## 8. 可复用的代码片段

### 8.1 Funding Z-Score 计算（直接复制）

```python
# 来源：funding_extreme.py:35-38 / pre_funding_unwind.py:35-38
funding_history = frame["funding_rate"].shift(1)  # 避免前视偏差
frame["funding_mean"] = funding_history.rolling(WINDOW, min_periods=MIN_PERIODS).mean()
frame["funding_std"] = funding_history.rolling(WINDOW, min_periods=MIN_PERIODS).std(ddof=0)
frame["funding_z"] = (frame["funding_rate"] - frame["funding_mean"]) / frame["funding_std"].replace(0, pd.NA)
```

### 8.2 OI Ratio 计算（直接复制）

```python
# 来源：funding_extreme.py:39 / pre_funding_unwind.py:39
frame["oi_ratio"] = frame["oi_value"] / frame["quote_volume"].replace(0, pd.NA)
```

### 8.3 时间窗口过滤（Gamma 必需）

```python
# 来源：pre_funding_unwind.py:49-56
funding_time = row.get("next_funding_time")
if pd.isna(funding_time):
    continue

now = frame.index[idx]
minutes_to_settlement = (pd.Timestamp(funding_time) - now).total_seconds() / 60.0
if minutes_to_settlement < MIN_MINUTES or minutes_to_settlement > MAX_MINUTES:
    continue
```

### 8.4 1:1 止损止盈结构（直接复制）

```python
# 来源：funding_extreme.py:62-76 / pre_funding_unwind.py:72-87
direction = -1 if float(funding_z) > 0 else 1
entry_price = float(row["close"])
stop_distance = max(float(row["high"] - row["low"]), entry_price * MIN_STOP_PCT)
stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
target_price = entry_price - stop_distance if direction < 0 else entry_price + stop_distance
valid_until_ts = ...  # 策略自定义

signals.append({
    "entry_ts": frame.index[idx],
    "valid_until_ts": valid_until_ts,
    "signal": direction,
    "entry_price": entry_price,
    "target_price": target_price,
    "stop_price": stop_price,
})
```

---

## 9. Alpha / Gamma 实现建议

### 9.1 Alpha（Funding Regime Switch）

**建议复用 Edge B 结构，修改点：**

1. **Regime 检测：** 在 `funding_z` 基础上增加 regime 分类（如 `funding_z > 2.0` 持续 N 期 = "extreme_long_regime"）
2. **切换逻辑：** 当 regime 从 normal 切换到 extreme 时开仓；当 regime 回归 normal 时平仓（而非固定时间止损）
3. **数据需求：** 可能需要更长的 funding 历史（如 500 bar）用于 regime 识别

**配置建议：**
```python
config = StrategyConfig(
    name="funding_regime_switch",
    leverage_cap=8.0,
    risk_per_trade_R=0.20,
    universe_fn=static_universe([]),
    bar_freq="1h",          # 同 Edge B
    is_event_driven=False,
    metadata={"edge": "Alpha"},
)
```

### 9.2 Gamma（Settlement Compression）

**建议复用 Edge E 结构，修改点：**

1. **时间窗口收紧：** 将 `5~60` 分钟改为更精确的窗口（如 `10~30` 分钟）
2. **压缩幅度预测：** 增加波动率指标（如 ATR）预测 settlement 后的预期波动
3. **提前平仓：** 在 settlement 发生后立即平仓（而非等待 30 分钟）

**配置建议：**
```python
config = StrategyConfig(
    name="settlement_compression",
    leverage_cap=8.0,
    risk_per_trade_R=0.18,   # 同 Edge E
    universe_fn=static_universe([]),
    bar_freq="10m",          # 同 Edge E
    is_event_driven=False,
    metadata={"edge": "Gamma"},
)
```

---

## 10. 文件路径索引

| 文件 | 路径 | 用途 |
|------|------|------|
| Edge B 策略 | `src/backtest/strategies/funding_extreme.py` | 参考实现 |
| Edge E 策略 | `src/backtest/strategies/pre_funding_unwind.py` | 参考实现 |
| 策略基类 | `src/backtest/strategies/base.py` | 接口契约 |
| 策略注册表 | `src/backtest/strategies/__init__.py` | 注册新策略 |
| 回测编排 | `src/backtest/run.py` | 数据加载 + 执行 |
| Funding 数据 | `src/data/okx_funding.py` | OKX API 封装 |
| 回测引擎 | `src/backtest/engine.py` | PnL 计算 |
| Edge B 测试 | `src/backtest/tests/test_funding_extreme_strategy.py` | 测试模板 |
| Edge E 测试 | `src/backtest/tests/test_pre_funding_unwind_strategy.py` | 测试模板 |

---

*本文档基于现有代码库的精确阅读，所有行号引用均对应 2026-06-28 的代码版本。*
