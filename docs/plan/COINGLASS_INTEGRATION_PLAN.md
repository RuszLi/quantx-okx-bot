# Phase 0.5 — Coinglass 真实清算数据接入方案

**目标**：用 Coinglass 真实清算方向数据替换 Phase 0 中的 OI 代理，重跑回测，验证策略假说是否在真实数据下成立。

---

## 0. 背景与核心修复点

Phase 0 失败根因是数据，不是策略逻辑：

| 组件 | Phase 0（OI 代理） | Phase 0.5（Coinglass 真实数据） |
|---|---|---|
| `liq_buy_usd` / `liq_sell_usd` | 全 NaN → fallback OI diff | Coinglass 实际 long/short 清算 USD |
| `cond_single_side` | taker buy/sell ratio（无法代理清算方向） | `max(liq_buy, liq_sell) / total > 0.80` |
| 信号方向 | `flow_imbalance` 正负 | `liq_sell > liq_buy` → LONG, 反向 → SHORT |
| `cond_volume` | OI drop 噪声 | 真实清算总量 |

修改涉及 **3 个现有文件** + **1 个新模块**（3 个文件）。

---

## 1. 前提：API 密钥

**路径 A（付费，推荐）**：Coinglass Hobbyist 计划 $29/月，注册后获取 API Key。

**路径 B（先免费试）**：测试旧 public endpoint 是否仍可访问（无需 key）：
```
GET https://open-api.coinglass.com/public/v2/liquidation?symbol=BTC&time_type=0
```
如果返回 200，则不需要付费 key。如果返回 403/401，走路径 A。

**配置**：将 key 写入项目根目录 `.env`：
```
COINGLASS_API_KEY=your_key_here
```
如果走路径 B（无 key），该变量设为空字符串即可，代码会自动切换 endpoint。

---

## 2. 新模块：`src/coinglass/`

### 2.1 `src/coinglass/__init__.py`
空文件。

---

### 2.2 `src/coinglass/client.py`

**职责**：封装 HTTP 请求，处理 rate limit 和重试。

```python
BASE_V4  = "https://open-api-v4.coinglass.com"
BASE_V2  = "https://open-api.coinglass.com/public/v2"  # fallback, no key
```

**唯一公开函数**：

```python
def get_agg_liq_history(
    symbol: str,        # e.g. "BTC" (strip "USDT" suffix before calling)
    interval: str,      # "1h" only — coinglass minimum granularity
    start_ms: int,      # Unix timestamp milliseconds
    end_ms: int,        # Unix timestamp milliseconds
    api_key: str = "",  # empty string → use V2 public endpoint
) -> list[dict]:
    """
    Returns list of dicts. Each dict:
      {
        "t":                  1716163200000,   # timestamp ms (bar open)
        "longLiquidationUsd":  234567.89,      # shorts liquidated → forced buy
        "shortLiquidationUsd": 12345.67,       # longs liquidated → forced sell
      }

    V4 endpoint (with key):
      GET /api/futures/liquidation/aggregated-history
      Headers: {"CG-API-KEY": api_key}
      Params: symbol, interval, startTime, endTime

    V2 fallback (no key):
      GET /public/v2/liquidation
      Params: symbol, time_type=0 (hourly), startTime, endTime

    V2 field mapping if different names:
      "createTime" → "t"
      "buyVolUsd"  → "longLiquidationUsd"
      "sellVolUsd" → "shortLiquidationUsd"

    Rate limit: sleep 0.25s between calls (≤ 240 calls/min on hobbyist).
    Retry: up to 3 times on 429/5xx with exponential backoff (2s, 4s, 8s).
    Raises: RuntimeError on auth failure (401/403) or data empty after retries.
    """
```

**symbol 格式转换** (内部 helper)：
```python
def _to_coinglass_symbol(okx_symbol: str) -> str:
    # "SOLUSDT" → "SOL", "BTCUSDT" → "BTC"
    return okx_symbol.replace("USDT", "").replace("_PERP", "")
```

---

### 2.3 `src/coinglass/downloader.py`

**职责**：按 symbol + 日期范围下载并缓存为 CSV。

**缓存路径**：`data/coinglass/{SYMBOL}_liq_{START}_{END}.csv`

**CSV 列**：`ts_ms, long_liq_usd, short_liq_usd`（ts_ms 为小时级 Unix ms）

**公开函数**：

```python
def download_liq(
    symbols: list[str],     # e.g. ["SOLUSDT", "DOGEUSDT"]
    start: date,
    end: date,
    api_key: str = "",
    force: bool = False,    # re-download even if cache exists
) -> dict[str, Path]:
    """
    For each symbol:
      1. Check if cache file exists and force=False → skip
      2. Call client.get_agg_liq_history() in chunks of 200 bars
         (200h ≈ 8 days; loop until end covered)
      3. Write CSV to data/coinglass/{SYMBOL}_liq_{start}_{end}.csv
    Returns: {symbol: cache_path}
    """
```

**CLI entry point** (so it can be run standalone):
```
python -m src.coinglass.downloader \
  --symbols SOLUSDT DOGEUSDT LTCUSDT \
  --start 2026-05-17 --end 2026-05-31
```
Reads `COINGLASS_API_KEY` from `.env` automatically.

---

## 3. 修改：`src/backtest/loader.py`

### 3.1 新增函数 `load_coinglass_liq()`

在 `load_liquidations()` 之后添加：

```python
def load_coinglass_liq(symbol: str, start: date, end: date) -> pd.DataFrame:
    """
    Reads cached Coinglass CSV for symbol.
    Returns 1-min indexed DataFrame with columns:
      liq_buy_usd   float64   (shortLiquidationUsd: long positions forced to sell)
      liq_sell_usd  float64   (longLiquidationUsd: short positions forced to buy)

    NOTE direction semantics (important for features.py):
      longLiquidationUsd  → shorts being liquidated → forced BUY → maps to liq_BUY_usd
      shortLiquidationUsd → longs being liquidated  → forced SELL → maps to liq_SELL_usd

    Hourly data is uniformly distributed across 60 1-min bars:
      each_min_value = hourly_value / 60.0

    Returns empty DataFrame if cache file not found.
    """
    cache_dir = DATA_ROOT / "coinglass"
    pattern = cache_dir / f"{symbol}_liq_*_*.csv"
    files = sorted(cache_dir.glob(f"{symbol}_liq_*.csv"))
    if not files:
        return pd.DataFrame()
    ...
    # Read CSV, parse ts_ms → UTC datetime index, distribute to 1-min, return
```

### 3.2 修改 `build_raw()` 中的清算加载逻辑

找到现有代码块（`loader.py` 约 192-208 行）：
```python
# Liquidations
liq = load_liquidations(symbol, start, end)
if not liq.empty and "usd" in liq.columns and "side" in liq.columns:
    ...
else:
    raw["liq_buy_usd"] = np.nan
    raw["liq_sell_usd"] = np.nan
```

**替换为**（三级优先级）：
```python
# Liquidations: try Coinglass first, then Binance snapshot, then leave NaN (OI proxy in features.py)
cg_liq = load_coinglass_liq(symbol, start, end)
if not cg_liq.empty:
    raw["liq_buy_usd"]  = cg_liq["liq_buy_usd"].reindex(master, fill_value=0.0)
    raw["liq_sell_usd"] = cg_liq["liq_sell_usd"].reindex(master, fill_value=0.0)
else:
    liq = load_liquidations(symbol, start, end)          # Binance (still 404, kept for future)
    if not liq.empty and "usd" in liq.columns and "side" in liq.columns:
        ...  # existing code unchanged
    else:
        raw["liq_buy_usd"]  = np.nan
        raw["liq_sell_usd"] = np.nan
```

---

## 4. 修改：`src/backtest/features.py`

`compute_features()` 内，在现有 `_liq_source` 判断块之后，新增一个 **REAL 数据路径**（features.py:65-78 附近）。

### 4.1 修改清算量计算 + single_side_ratio

将现有代码：
```python
liq_total = df["liq_buy_usd"].fillna(0.0) + df["liq_sell_usd"].fillna(0.0)

if liq_total.sum() == 0.0 or df["liq_buy_usd"].isna().all():
    oi_drop = ...
    _liq_source = "OI_PROXY"
else:
    _liq_source = "REAL"

df["liq_usd_60s"] = liq_total.rolling(...).sum()
```

**替换为**：
```python
liq_buy  = df["liq_buy_usd"].fillna(0.0)
liq_sell = df["liq_sell_usd"].fillna(0.0)
liq_total = liq_buy + liq_sell

if liq_total.sum() == 0.0 or df["liq_buy_usd"].isna().all():
    # OI proxy path (unchanged)
    oi_drop = (-df["oi_value_diff_5m"].fillna(0.0)).clip(lower=0)
    oi_drop_per_min = oi_drop / 5.0
    liq_total = oi_drop_per_min
    liq_buy   = liq_total * 0.5   # symmetrical fallback, direction from flow_imbalance
    liq_sell  = liq_total * 0.5
    _liq_source = "OI_PROXY"
else:
    _liq_source = "REAL"

flow_roll_bars = max(1, params.liq_rolling_sec // 60)
df["liq_buy_60s"]  = liq_buy.rolling(flow_roll_bars, min_periods=1).sum()
df["liq_sell_60s"] = liq_sell.rolling(flow_roll_bars, min_periods=1).sum()
df["liq_usd_60s"]  = df["liq_buy_60s"] + df["liq_sell_60s"]

# single_side_ratio: real direction for REAL, flow_imbalance proxy for OI_PROXY
if _liq_source == "REAL":
    eps = 1e-9
    df["single_side_ratio"] = (
        df[["liq_buy_60s", "liq_sell_60s"]].max(axis=1)
        / (df["liq_usd_60s"] + eps)
    )
    # Direction column: +1 if buy (short squeeze), -1 if sell (long cascade)
    df["liq_direction"] = np.where(df["liq_buy_60s"] >= df["liq_sell_60s"], +1.0, -1.0)
else:
    # existing flow_imbalance code (unchanged)
    df["flow_imbalance"] = ...
    df["single_side_ratio"] = df["flow_imbalance"].abs()
    df["liq_direction"] = np.sign(df["flow_imbalance"])
```

### 4.2 修改 `cond_decelerating` — 适配小时粒度

将现有：
```python
df["liq_accel"] = df["liq_usd_60s"].diff().diff()
df["cond_decelerating"] = df["liq_accel"] < 0
```

**替换为**：
```python
if _liq_source == "REAL":
    # Hourly data: within-hour diff is 0 (constant). Use 60-bar MA derivative.
    liq_ma60 = df["liq_usd_60s"].rolling(60, min_periods=1).mean()
    df["liq_accel"] = liq_ma60.diff()
    df["cond_decelerating"] = df["liq_accel"] < 0
else:
    df["liq_accel"] = df["liq_usd_60s"].diff().diff()
    df["cond_decelerating"] = df["liq_accel"] < 0
```

### 4.3 修改信号方向 — 使用 `liq_direction` 替代 `flow_imbalance`

将现有：
```python
long_mask  = all_cond & (df["displacement"] < -params.displacement_min_atr) & (df["flow_imbalance"] < 0)
short_mask = all_cond & (df["displacement"] > params.displacement_min_atr)  & (df["flow_imbalance"] > 0)
```

**替换为**：
```python
long_mask  = all_cond & (df["displacement"] < -params.displacement_min_atr) & (df["liq_direction"] < 0)
short_mask = all_cond & (df["displacement"] > params.displacement_min_atr)  & (df["liq_direction"] > 0)
```

（`liq_direction` 在两个路径下均已计算，接口一致。）

---

## 5. 执行顺序

```bash
# Step 1: 下载 Coinglass 历史清算数据（约 20 symbols × 15 天 = 72 API calls）
python -m src.coinglass.downloader \
  --symbols ADAUSDT APTUSDT ARBUSDT ATOMUSDT BCHUSDT DOGEUSDT DOTUSDT \
           FETUSDT FILUSDT INJUSDT LDOUSDT LINKUSDT LTCUSDT POLUSDT \
           RENDERUSDT SEIUSDT SOLUSDT SUIUSDT WIFUSDT \
  --start 2026-05-17 --end 2026-05-31

# Step 2: 清除旧 processed cache（否则 build_raw 会跳过重建）
rm data/processed/*_raw.parquet

# Step 3: 重跑回测
python -m src.backtest.run \
  --universe src/backtest/symbol_universe.json \
  --start 2026-05-17 --end 2026-05-31 \
  --out reports_v2/
```

Step 3 输出最后一行会显示 `Liq source: REAL`，确认数据已切换。

---

## 6. 验证检查清单（编码完成后逐项确认）

- [ ] `src/coinglass/downloader.py` 运行后 `data/coinglass/SOLUSDT_liq_*.csv` 存在，行数 = 预期小时数（15天 × 24h = 360 行）
- [ ] CSV 中 `long_liq_usd` 和 `short_liq_usd` 无全零列（至少 50% 非零）
- [ ] `load_coinglass_liq("SOLUSDT", ...)` 返回 DataFrame，index 为 1-min UTC，每小时的60行值相同（均匀分配验证）
- [ ] `build_raw("SOLUSDT", ...)` 返回 DataFrame，`liq_buy_usd.isna().sum() == 0`
- [ ] `compute_features(raw).attrs["liq_source"] == "REAL"` 且 `features["signal"].abs().sum() > 0`（有信号）

---

## 7. 已知约束

| 项目 | 说明 |
|---|---|
| 数据粒度 | Coinglass 最细 1h；1-min 内等分分配，精度低于 tick 级 |
| `cond_decelerating` | 1h 粒度下改为 60-bar MA 一阶差分，语义微变（"本小时比过去1小时低"）|
| Coinglass symbol 格式 | 去掉 USDT 后缀："SOLUSDT" → "SOL"；如果 API 返回 404，需确认实际 symbol 格式 |
| API Key | V4 需付费 key；优先测试 V2 public endpoint，若 403 则切换 V4 |
| 跨所覆盖 | Coinglass aggregated-history 跨 Binance/Bybit/OKX 聚合，优于单所 OI |
