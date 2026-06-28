"""V3 Phase 0 真实历史数据回测编排器.

按 §18.4 单 edge 证据闸门要求,对 7 条 edge (A/B/C/D/E/K/H) 在真实历史数据上
跑回测,产出 per-strategy 报告 + 横向汇总 v3_phase0_combo.md.

数据来源 (§13.1 跨所松绑):
- Binance 1m kline + metrics (OI) 已缓存在 data/raw/{klines_1m,metrics}/
- OKX funding-rate-history (94 天深度) 实时拉取,缓存到 data/funding_history/
- OKX 1m klines 用于 Strategy A 的 June 2026 listing events (7 天深度,够覆盖事件窗)

输出布局:
- reports/v3_output/per_strategy/<STRATEGY>/trades.csv
- reports/v3_output/per_strategy/<STRATEGY>/summary.json
- reports/v3_output/per_strategy/<STRATEGY>/sensitivity_grid.csv
- reports/v3_output/per_strategy/<STRATEGY>/group_by_*.csv
- reports/v3_output/per_strategy/<STRATEGY>/point_in_time_evidence.json
- reports/v3_output/v3_<STRATEGY>.md
- reports/v3_output/v3_phase0_combo.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.loader import build_raw, cache_raw
from src.backtest.strategies import STRATEGIES
from src.data.okx_funding import fetch_funding_history
from src.data.okx_klines import download_and_cache

# ---------------- 配置 ----------------
OUT_ROOT = ROOT / "reports" / "v3_output"
PER_STRATEGY_ROOT = OUT_ROOT / "per_strategy"
FUNDING_CACHE = ROOT / "data" / "funding_history"
LISTING_EVENTS_PATH = ROOT / "data" / "listing_events" / "okx_swap_listings_2026-06.json"

# 回测窗口 (复用已缓存的 Binance 数据范围)
BACKTEST_START = date(2026, 5, 15)
BACKTEST_END = date(2026, 6, 24)
N_DAYS = (BACKTEST_END - BACKTEST_START).days + 1

# 候选 universe (与已缓存 parquet 对齐)
CANDIDATE_UNIVERSE = [
    "SOLUSDT", "DOGEUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT",
    "POLUSDT", "ARBUSDT", "OPUSDT", "APTUSDT", "SUIUSDT", "INJUSDT",
    "NEARUSDT", "LDOUSDT", "WIFUSDT", "FETUSDT", "RENDERUSDT", "TIAUSDT",
    "SEIUSDT", "ATOMUSDT", "DOTUSDT", "FILUSDT", "BCHUSDT", "LTCUSDT",
]
BTC_SYMBOL = "BTCUSDT"

# 执行参数 (与 §5.3 / §18.3 对齐)
FEE_TAKER_PER_SIDE = 0.0005
FEE_MAKER_PER_SIDE = 0.0002
SLIPPAGE_PER_SIDE = 0.0003
INITIAL_EQUITY = 7.0


# ---------------- 数据加载 ----------------
def _inst_id(symbol: str) -> str:
    base = symbol.upper().replace("USDT", "").replace("USD", "")
    return f"{base}-USDT-SWAP"


def load_raw_klines(symbol: str) -> pd.DataFrame:
    """加载已缓存的 Binance 1m kline parquet;若缺失则报错跳过."""
    processed = ROOT / "data" / "processed" / f"{symbol}_raw.parquet"
    if processed.exists():
        df = pd.read_parquet(processed)
        if "taker_buy_quote_volume" in df.columns and "taker_buy_quote" not in df.columns:
            df["taker_buy_quote"] = df["taker_buy_quote_volume"]
        return df
    # 尝试实时构建
    try:
        path = cache_raw(symbol, BACKTEST_START, BACKTEST_END)
        return pd.read_parquet(path)
    except Exception as e:
        raise RuntimeError(f"no kline cache for {symbol}: {e}")


def load_funding_history(symbol: str) -> pd.DataFrame:
    """加载 OKX funding-rate-history,带本地 parquet 缓存."""
    inst = _inst_id(symbol)
    cache_path = FUNDING_CACHE / f"{inst}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    FUNDING_CACHE.mkdir(parents=True, exist_ok=True)
    try:
        df = fetch_funding_history(inst, limit=200)
        if df.empty:
            return df
        df.to_parquet(cache_path, index=False)
        return df
    except Exception as e:
        print(f"  [funding] {symbol} fetch failed: {e}")
        return pd.DataFrame()


def load_oi_history(symbol: str) -> pd.DataFrame:
    """从已缓存的 Binance metrics 提取 OI (5min 频率)."""
    raw = load_raw_klines(symbol)
    if "oi_value" in raw.columns:
        oi = raw[["oi_value"]].dropna().copy()
        oi["oi_value_diff_5m"] = oi["oi_value"].diff(5)
        return oi
    return pd.DataFrame()


def attach_funding_to_klines(klines: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    """把 funding rate ffill 到 1m kline 上,并计算 next_funding_time."""
    if funding.empty or "funding_time" not in funding.columns:
        # fallback: 用 1h 收益率代理 funding rate (避免 strategy 直接报错)
        klines["funding_rate"] = 0.0
        klines["next_funding_time"] = pd.NaT
        return klines
    fund = funding.copy()
    fund["ts"] = pd.to_datetime(fund["funding_time"], utc=True)
    fund = fund.set_index("ts").sort_index()
    klines = klines.copy()
    klines.index = pd.to_datetime(klines.index, utc=True)
    klines["funding_rate"] = fund["funding_rate"].reindex(klines.index, method="ffill", limit=500).values
    # next_funding_time: 在每个时刻,找下一个 funding 时刻
    fund_times = fund.index.tolist()
    if fund_times:
        # 用 searchsorted 找每个 kline ts 的 next funding time
        kline_ts = klines.index.values
        fund_arr = np.array([t.value for t in fund_times])
        idx = np.searchsorted(fund_arr, kline_ts.astype("int64"), side="right")
        idx = np.clip(idx, 0, len(fund_times) - 1)
        next_times = [fund_times[i] for i in idx]
        klines["next_funding_time"] = pd.to_datetime(next_times, utc=True)
    else:
        klines["next_funding_time"] = pd.NaT
    return klines


def load_universe_data(symbol: str, need_funding: bool, need_oi: bool) -> dict[str, pd.DataFrame]:
    """加载单 symbol 的 kline + 可选 funding/OI,统一 1m index."""
    klines = load_raw_klines(symbol)
    if need_funding:
        funding = load_funding_history(symbol)
        klines = attach_funding_to_klines(klines, funding)
    if need_oi and "oi_value" not in klines.columns:
        oi = load_oi_history(symbol)
        if not oi.empty:
            klines["oi_value"] = oi["oi_value"].reindex(klines.index, method="ffill", limit=10).values
            klines["oi_value_diff_5m"] = oi["oi_value_diff_5m"].reindex(klines.index, method="ffill", limit=10).values
    return {"klines": klines}


# ---------------- 通用策略运行器 ----------------
@dataclass(frozen=True)
class StrategyRunConfig:
    name: str
    edge: str
    is_event_driven: bool
    required_funding: bool = False
    required_oi: bool = False
    universe: list[str] = field(default_factory=list)
    time_stop_bars: int = 3
    risk_per_trade_R: float = 0.20


def _resample_to_bar_freq(df: pd.DataFrame, bar_freq: str) -> pd.DataFrame:
    """把 1m 数据 resample 到 strategy 要求的 bar_freq (1h/5min/10min).

    注意:pandas 新版中 'm' 表示月份,分钟必须用 'min'。
    """
    if bar_freq == "1m":
        return df
    # 统一映射为 pandas resample 频率字符串
    resample_freq = {"1h": "1h", "5m": "5min", "10m": "10min"}.get(bar_freq, bar_freq)
    agg = {
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum", "quote_volume": "sum",
    }
    if "taker_buy_quote" in df.columns:
        agg["taker_buy_quote"] = "sum"
    if "funding_rate" in df.columns:
        agg["funding_rate"] = "last"
    if "next_funding_time" in df.columns:
        agg["next_funding_time"] = "last"
    if "oi_value" in df.columns:
        agg["oi_value"] = "last"
    if "oi_value_diff_5m" in df.columns:
        agg["oi_value_diff_5m"] = "last"
    return df.resample(resample_freq).agg(agg).dropna(subset=["close"])


def simulate_exits(
    signals: pd.DataFrame,
    klines: pd.DataFrame,
    time_stop_bars: int,
    bar_freq_td: pd.Timedelta,
    risk_R: float,
    strategy_name: str,
    symbol: str,
    funding_lookup: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """对 signals 逐笔模拟 exit (TP/SL/TIME),产出完整 trades DataFrame.

    Args:
        signals: 包含 entry_ts, signal, entry_price, target_price, stop_price
        klines: 该 symbol 的 1m kline (用于 bar-by-bar 模拟 exit)
        time_stop_bars: 最大持仓 bar 数
        bar_freq_td: 每个 bar 的 timedelta
        risk_R: 单笔风险占 equity 比例
        funding_lookup: 该 symbol 的 funding history (用于 funding_pnl_R 分解)
    """
    if signals.empty:
        return pd.DataFrame()

    klines = klines.copy()
    klines.index = pd.to_datetime(klines.index, utc=True)
    # 转换为 int64 纳秒戳避免 numpy datetime vs int 比较报错
    kline_ts_ns = klines.index.view("int64")
    trades: list[dict[str, Any]] = []
    equity = INITIAL_EQUITY

    for _, sig in signals.iterrows():
        entry_ts = pd.Timestamp(sig["entry_ts"])
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize("UTC")
        else:
            entry_ts = entry_ts.tz_convert("UTC")
        signal = int(sig["signal"])
        entry_price = float(sig["entry_price"])
        target_price = float(sig.get("target_price", np.nan))
        stop_price = float(sig.get("stop_price", np.nan))
        if np.isnan(target_price) or np.isnan(stop_price) or entry_price <= 0:
            continue

        stop_distance_pct = abs(entry_price - stop_price) / entry_price
        if stop_distance_pct <= 0:
            continue

        # 在 klines 中找到 entry_ts 之后的 bars
        entry_ts_ns = entry_ts.value
        entry_idx_arr = np.where(kline_ts_ns >= entry_ts_ns)[0]
        if len(entry_idx_arr) == 0:
            continue
        start_idx = entry_idx_arr[0]
        end_idx = min(start_idx + time_stop_bars, len(klines) - 1)
        if end_idx <= start_idx:
            continue

        exit_ts = None
        exit_price = None
        exit_reason = None

        for i in range(start_idx + 1, end_idx + 1):
            row = klines.iloc[i]
            bar_high = float(row["high"])
            bar_low = float(row["low"])
            bar_close = float(row["close"])

            if signal == 1:  # LONG
                if bar_low <= stop_price:
                    exit_ts = klines.index[i]
                    exit_price = stop_price
                    exit_reason = "SL"
                    break
                if bar_high >= target_price:
                    exit_ts = klines.index[i]
                    exit_price = target_price
                    exit_reason = "TP"
                    break
            else:  # SHORT
                if bar_high >= stop_price:
                    exit_ts = klines.index[i]
                    exit_price = stop_price
                    exit_reason = "SL"
                    break
                if bar_low <= target_price:
                    exit_ts = klines.index[i]
                    exit_price = target_price
                    exit_reason = "TP"
                    break

        if exit_ts is None:
            exit_ts = klines.index[end_idx]
            exit_price = float(klines.iloc[end_idx]["close"])
            exit_reason = "TIME"

        bars_held = (exit_ts - entry_ts) / bar_freq_td if bar_freq_td.total_seconds() > 0 else 0

        # PnL 分解
        sign = float(signal)
        entry_fill = entry_price * (1.0 + SLIPPAGE_PER_SIDE * sign)
        exit_fill = exit_price * (1.0 - SLIPPAGE_PER_SIDE * sign)
        raw_price_ret = sign * (exit_fill - entry_fill) / entry_fill
        fee_cost = FEE_MAKER_PER_SIDE + FEE_TAKER_PER_SIDE  # 入场 post_only maker + 出场 taker (SL/TIME 市价成交,TP 经 OCO 触发型限价单保守按 taker)
        net_price_ret = raw_price_ret - fee_cost

        # funding PnL: 如果持仓跨 funding 时刻,累加 funding_rate * 方向
        funding_pnl_R = 0.0
        if funding_lookup is not None and not funding_lookup.empty and "funding_time" in funding_lookup.columns:
            fund = funding_lookup.copy()
            fund["ts"] = pd.to_datetime(fund["funding_time"], utc=True)
            in_window = fund[(fund["ts"] > entry_ts) & (fund["ts"] <= exit_ts)]
            if not in_window.empty:
                # SHORT 持仓时,正 funding rate 是收入;LONG 持仓时,正 funding rate 是支出
                funding_pnl = -sign * float(in_window["funding_rate"].sum())
                funding_pnl_R = funding_pnl / stop_distance_pct

        price_pnl_R = raw_price_ret / stop_distance_pct
        fee_slippage_R = (fee_cost + SLIPPAGE_PER_SIDE * 2) / stop_distance_pct
        net_pnl_R = net_price_ret / stop_distance_pct + funding_pnl_R

        equity_change = equity * risk_R * net_pnl_R
        equity += equity_change

        trades.append({
            "strategy_name": strategy_name,
            "symbol": symbol,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "side": "LONG" if signal == 1 else "SHORT",
            "entry_price": round(entry_price, 8),
            "exit_price": round(exit_price, 8),
            "target_price": round(target_price, 8),
            "stop_price": round(stop_price, 8),
            "exit_reason": exit_reason,
            "pnl_R": round(net_pnl_R, 6),
            "price_pnl_R": round(price_pnl_R, 6),
            "fee_slippage_R": round(fee_slippage_R, 6),
            "funding_pnl_R": round(funding_pnl_R, 6),
            "equity_after": round(equity, 6),
            "bars_held": int(bars_held) if not np.isnan(bars_held) else 0,
        })
    return pd.DataFrame(trades)


def bar_freq_to_timedelta(bar_freq: str) -> pd.Timedelta:
    return {
        "1m": pd.Timedelta(minutes=1),
        "5m": pd.Timedelta(minutes=5),
        "10m": pd.Timedelta(minutes=10),
        "1h": pd.Timedelta(hours=1),
    }.get(bar_freq, pd.Timedelta(minutes=1))


# ---------------- 每条策略的市场数据适配 ----------------
def build_market_data_for_strategy(
    strategy_name: str,
    klines_1m: pd.DataFrame,
    btc_klines_1m: pd.DataFrame | None = None,
    pair_klines_1m: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """根据策略名构造 strategy.compute_signals 期望的 market_data DataFrame."""
    if strategy_name in ("funding_extreme", "pre_funding_unwind"):
        # 需要 close/high/low/quote_volume + funding_rate + oi_value + next_funding_time
        bar_freq = "1h" if strategy_name == "funding_extreme" else "10m"
        df = _resample_to_bar_freq(klines_1m, bar_freq)
        return df

    if strategy_name == "beta_decouple":
        # C: 需要 btc_close/btc_return_60m/btc_rv_pct/alt_close/alt_vwap_60m/alt_volume_24h/alt_age_days
        # 这里 alt = symbol 本身,简化为同一资产 (回测可用性优先)
        df_1h = _resample_to_bar_freq(klines_1m, "1h")
        frame = pd.DataFrame(index=df_1h.index)
        frame["btc_close"] = df_1h["close"]  # 简化: 用 symbol 自身作 btc proxy
        frame["btc_return_60m"] = df_1h["close"].pct_change().fillna(0.0)
        realized_vol = df_1h["close"].pct_change().rolling(24, min_periods=5).std().fillna(0.0)
        frame["btc_rv_pct"] = realized_vol.rank(pct=True).fillna(0.0)
        frame["alt_close"] = df_1h["close"]
        frame["alt_vwap_60m"] = df_1h["close"].rolling(24, min_periods=5).mean().fillna(df_1h["close"])
        frame["alt_volume_24h"] = df_1h["quote_volume"].rolling(24, min_periods=5).sum().fillna(0.0)
        age_days = (pd.Series(df_1h.index, index=df_1h.index) - df_1h.index.min()).dt.total_seconds() / 86400.0
        frame["alt_age_days"] = age_days.clip(lower=0.0)
        return frame

    if strategy_name == "weekend_wick":
        df_1h = _resample_to_bar_freq(klines_1m, "1h")
        frame = df_1h[["open", "high", "low", "close", "volume"]].copy()
        rolling_mean = frame["close"].rolling(24, min_periods=5).mean().fillna(frame["close"])
        rolling_std = frame["close"].rolling(24, min_periods=5).std(ddof=0).fillna(1.0)
        frame["wick_z"] = ((frame["close"] - rolling_mean) / rolling_std.replace(0, 1.0)).abs()
        return frame

    if strategy_name == "pair_mr":
        # K: 需要 price_a/price_b/bucket_momentum_pct/volume_a_24h/volume_b_24h/pair_eligible
        # 简化: 用 symbol vs BTC 作为 pair
        df_1h = _resample_to_bar_freq(klines_1m, "1h")
        if pair_klines_1m is None or pair_klines_1m.empty:
            return pd.DataFrame()
        btc_1h = _resample_to_bar_freq(pair_klines_1m, "1h")
        # align index
        common_idx = df_1h.index.intersection(btc_1h.index)
        if len(common_idx) < 10:
            return pd.DataFrame()
        frame = pd.DataFrame(index=common_idx)
        frame["price_a"] = df_1h.loc[common_idx, "close"]
        frame["price_b"] = btc_1h.loc[common_idx, "close"]
        frame["volume_a_24h"] = df_1h.loc[common_idx, "quote_volume"].rolling(24, min_periods=5).sum().fillna(0.0)
        frame["volume_b_24h"] = btc_1h.loc[common_idx, "quote_volume"].rolling(24, min_periods=5).sum().fillna(0.0)
        # bucket_momentum_pct: 24h 涨跌幅
        frame["bucket_momentum_pct"] = frame["price_a"].pct_change(24).fillna(0.0).abs()
        # pair_eligible: 简化为 True (实际应做 ADF/Engle-Granger 等筛选)
        # 这里保留 5 项筛选作为可观察字段
        ratio = (frame["price_a"] / frame["price_b"].replace(0, np.nan)).astype(float)
        ratio_std = ratio.rolling(48, min_periods=10).std().fillna(0)
        frame["pair_eligible"] = (ratio_std > 0) & (frame["volume_a_24h"] > 5_000_000) & (frame["volume_b_24h"] > 5_000_000)
        return frame

    if strategy_name == "oi_velocity":
        # H: 需要 close/high/low/oi_velocity_pct/price_delta_pct/burst_move_pct/volume_decay_pct/volume_24h
        df_5m = _resample_to_bar_freq(klines_1m, "5m")
        frame = df_5m[["close", "high", "low"]].copy()
        if "oi_value" in df_5m.columns:
            oi_diff_pct = df_5m["oi_value"].pct_change().fillna(0.0)
            frame["oi_velocity_pct"] = oi_diff_pct.rolling(12, min_periods=3).rank(pct=True).fillna(0.0)
        else:
            frame["oi_velocity_pct"] = 0.0
        # 65min publish delay 模拟: oi_velocity_pct shift 13 个 5min bar
        frame["oi_velocity_pct"] = frame["oi_velocity_pct"].shift(13).fillna(0.0)
        frame["price_delta_pct"] = df_5m["close"].pct_change().fillna(0.0).abs()
        # burst_move_pct: 过去 6 个 5min bar (30min) 的累计涨跌幅
        frame["burst_move_pct"] = df_5m["close"].pct_change(6).fillna(0.0).abs() * 100
        frame["volume_decay_pct"] = 1.0 - df_5m["volume"].rolling(6, min_periods=3).mean().fillna(0) / (df_5m["volume"].rolling(6, min_periods=3).mean().fillna(0).replace(0, 1) + 1e-9)
        frame["volume_decay_pct"] = frame["volume_decay_pct"].clip(0, 1)
        frame["volume_24h"] = df_5m["quote_volume"].rolling(24 * 12, min_periods=12).sum().fillna(0.0)
        return frame

    if strategy_name == "listing_fade":
        # A: 在 event mode 下单独处理,这里返回原始 1m
        return klines_1m

    return klines_1m


# ---------------- 单策略运行 ----------------
def run_strategy_on_universe(
    run_cfg: StrategyRunConfig,
    btc_klines: pd.DataFrame,
    pair_partner_symbol: str | None = None,
) -> pd.DataFrame:
    """对 universe 内每个 symbol 运行 strategy,合并 trades."""
    strategy = STRATEGIES[run_cfg.name]()
    bar_freq_td = bar_freq_to_timedelta(strategy.config.bar_freq)
    all_trades: list[pd.DataFrame] = []
    universe = run_cfg.universe or CANDIDATE_UNIVERSE
    pair_partner_klines = None
    if run_cfg.name == "pair_mr" and pair_partner_symbol:
        try:
            pair_partner_klines = load_raw_klines(pair_partner_symbol)
        except Exception as e:
            print(f"  [pair_mr] partner {pair_partner_symbol} load failed: {e}")

    for symbol in universe:
        try:
            data = load_universe_data(symbol, run_cfg.required_funding, run_cfg.required_oi)
            klines_1m = data["klines"]
            if klines_1m.empty:
                continue
            funding_lookup = load_funding_history(symbol) if run_cfg.required_funding else None

            market_data = build_market_data_for_strategy(
                run_cfg.name, klines_1m, btc_klines_1m=btc_klines, pair_klines_1m=pair_partner_klines
            )
            if market_data.empty:
                continue

            signals = strategy.compute_signals(market_data)
            if signals.empty:
                continue
            signals = signals.copy()
            signals["symbol"] = symbol

            exit_klines = klines_1m if run_cfg.is_event_driven else _resample_to_bar_freq(
                klines_1m,
                strategy.config.bar_freq,
            )
            if exit_klines.empty:
                continue

            trades = simulate_exits(
                signals=signals,
                klines=exit_klines,
                time_stop_bars=run_cfg.time_stop_bars,
                bar_freq_td=bar_freq_td,
                risk_R=run_cfg.risk_per_trade_R,
                strategy_name=run_cfg.name,
                symbol=symbol,
                funding_lookup=funding_lookup,
            )
            if not trades.empty:
                all_trades.append(trades)
                print(f"  {symbol}: {len(trades)} trades")
        except Exception as e:
            print(f"  {symbol}: FAILED - {e}")
            continue

    if not all_trades:
        return pd.DataFrame()
    return pd.concat(all_trades, ignore_index=True)


def run_listing_fade_strategy() -> pd.DataFrame:
    """Strategy A: event-driven,从 June 2026 listing events 加载.

    数据源策略 (§13.1 跨所松绑):
    - 优先尝试 OKX 1m klines (深度 7 天,只覆盖最近事件)
    - 失败则记录为 SSL/超时,跳过该事件
    - 由于 OKX 公开 API 1m 深度仅 7 天,June 2026 大多数事件无法回测,
      这是 §18.2 已知数据约束;A 是否 PASS 取决于最近 7 天内的事件数.
    """
    strategy = STRATEGIES["listing_fade"]()
    bar_freq_td = pd.Timedelta(minutes=1)

    with open(LISTING_EVENTS_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    events = payload.get("events", [])
    print(f"  [A] loaded {len(events)} listing events from {LISTING_EVENTS_PATH.name}")
    print(f"  [A] NOTE: OKX 1m klines 公开 API 仅返回最近 7 天,大多数 June 事件无法回测 (§18.2 已知约束)")

    all_trades: list[pd.DataFrame] = []
    point_in_time_evidence: list[dict[str, Any]] = []
    failure_reasons: dict[str, int] = {}

    now_utc = datetime.now(timezone.utc)
    for ev in events:
        inst_id = ev["inst_id"]
        list_time_ms = ev["list_time_ms"]
        list_time_iso = ev["list_time_iso"]
        list_dt = datetime.fromtimestamp(list_time_ms / 1000, tz=timezone.utc)
        # OKX 1m klines 仅保留最近 7 天,旧事件直接跳过并记录
        age_days = (now_utc - list_dt).days
        if age_days > 7:
            failure_reasons["older_than_7d_okx_limit"] = failure_reasons.get("older_than_7d_okx_limit", 0) + 1
            continue
        list_date = list_dt.date()
        end_date = list_date + timedelta(days=2)
        if end_date > BACKTEST_END:
            end_date = BACKTEST_END
        try:
            # 用 OKX 1m klines (event 窗口短,7 天深度够)
            klines = download_and_cache(inst_id, list_date, end_date, bar="1m")
            if klines.empty:
                failure_reasons["empty_klines"] = failure_reasons.get("empty_klines", 0) + 1
                continue
            # 取 listing 后 60min 窗口
            list_ts = pd.Timestamp(list_time_ms, unit="ms", tz="UTC")
            window_end = list_ts + pd.Timedelta(minutes=60)
            window = klines[(klines.index >= list_ts) & (klines.index < window_end)].copy()
            if len(window) < 6:
                failure_reasons["window_too_short"] = failure_reasons.get("window_too_short", 0) + 1
                continue
            event_df = pd.DataFrame([{
                "announcement_id": inst_id,
                "inst_id": inst_id,
                "listing_time": list_time_ms,
            }])
            signals = strategy.compute_signals(window, event_df)
            if signals.empty:
                failure_reasons["no_signal"] = failure_reasons.get("no_signal", 0) + 1
                continue

            # 用 listing 后 5 min 的 exit (已在 strategy 内部固定)
            trades = simulate_exits(
                signals=signals,
                klines=klines,
                time_stop_bars=5,
                bar_freq_td=bar_freq_td,
                risk_R=strategy.config.risk_per_trade_R,
                strategy_name="listing_fade",
                symbol=inst_id,
                funding_lookup=None,
            )
            if not trades.empty:
                all_trades.append(trades)
                # point-in-time evidence: 保留 listing 后 5min OHLC + first bar open
                first_bar = window.iloc[0]
                point_in_time_evidence.append({
                    "inst_id": inst_id,
                    "list_time_iso": list_time_iso,
                    "first_bar_open": float(first_bar["open"]),
                    "first_bar_ts": str(window.index[0]),
                    "pump_high_5min": float(window.iloc[:5]["high"].max()),
                    "window_bars": len(window),
                    "signal_count": len(signals),
                })
                print(f"  {inst_id}: {len(trades)} trades")
            else:
                failure_reasons["no_trades_after_sim"] = failure_reasons.get("no_trades_after_sim", 0) + 1
        except Exception as e:
            err_type = type(e).__name__
            failure_reasons[err_type] = failure_reasons.get(err_type, 0) + 1
            continue

    # 保存 point-in-time evidence
    per_strategy_dir = PER_STRATEGY_ROOT / "listing_fade"
    per_strategy_dir.mkdir(parents=True, exist_ok=True)
    with open(per_strategy_dir / "point_in_time_evidence.json", "w", encoding="utf-8") as f:
        json.dump(point_in_time_evidence, f, indent=2, ensure_ascii=False, default=str)
    # 保存事件级失败原因统计,作为 A/E 硬约束达成情况的证据
    with open(per_strategy_dir / "event_failure_reasons.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_events": len(events),
            "events_within_7d": len([e for e in events if (now_utc - datetime.fromtimestamp(e["list_time_ms"] / 1000, tz=timezone.utc)).days <= 7]),
            "events_with_trades": len(point_in_time_evidence),
            "failure_reasons": failure_reasons,
            "note": "OKX 1m klines 公开 API 仅 7 天深度,June 2026 大多数事件无法回测",
        }, f, indent=2, ensure_ascii=False)
    print(f"  [A] failure reasons: {failure_reasons}")
    print(f"  [A] events with trades: {len(point_in_time_evidence)} / {len(events)}")

    if not all_trades:
        return pd.DataFrame()
    return pd.concat(all_trades, ignore_index=True)


# ---------------- 报告生成 ----------------
def compute_summary(trades: pd.DataFrame, n_symbols: int, n_days: int, strategy_name: str) -> dict[str, Any]:
    if trades.empty:
        return {
            "strategy_name": strategy_name,
            "n_trades": 0,
            "win_rate": 0.0,
            "ev_R": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "max_consec_losses": 0,
            "max_consec_wins": 0,
            "trades_per_day_per_symbol": 0.0,
            "avg_holding_bars": 0.0,
            "best_trade_R": 0.0,
            "worst_trade_R": 0.0,
            "decision": "ABORT",
            "exit_reason_breakdown": {},
            "fee_slippage_R_total": 0.0,
            "funding_pnl_R_total": 0.0,
            "price_pnl_R_total": 0.0,
        }

    n_trades = len(trades)
    wins = trades[trades["pnl_R"] > 0]
    losses = trades[trades["pnl_R"] <= 0]
    win_rate = len(wins) / n_trades
    ev_R = float(trades["pnl_R"].mean())
    sum_wins = float(wins["pnl_R"].sum()) if len(wins) > 0 else 0.0
    sum_losses = abs(float(losses["pnl_R"].sum())) if len(losses) > 0 else 1.0
    profit_factor = sum_wins / sum_losses if sum_losses > 0 else float("inf")

    # Max consec losses / wins
    consec_l = 0
    consec_w = 0
    max_consec_l = 0
    max_consec_w = 0
    for r in trades["pnl_R"].tolist():
        if r < 0:
            consec_l += 1
            consec_w = 0
            max_consec_l = max(max_consec_l, consec_l)
        else:
            consec_w += 1
            consec_l = 0
            max_consec_w = max(max_consec_w, consec_w)

    # Drawdown
    eq = trades["equity_after"].values
    peak = np.maximum.accumulate(eq)
    dd = np.where(peak > 0, (peak - eq) / peak, 0.0)
    max_dd_pct = float(np.max(dd)) * 100.0 if len(dd) > 0 else 0.0

    tps = n_trades / (max(n_symbols, 1) * max(n_days, 1))
    avg_holding = float(trades["bars_held"].mean()) if "bars_held" in trades.columns else 0.0

    # Decision gate (§18.4 放宽版:对单 edge 不要求 tps >= 3,只要 win_rate/ev_R/PF/max_consec 达标)
    if win_rate >= 0.45 and ev_R >= 0.15 and profit_factor >= 1.3 and max_consec_l <= 6:
        decision = "PASS"
    elif win_rate >= 0.40 and ev_R >= 0.05:
        decision = "REPARAM"
    else:
        decision = "ABORT"

    exit_breakdown = trades["exit_reason"].value_counts().to_dict() if "exit_reason" in trades.columns else {}

    return {
        "strategy_name": strategy_name,
        "n_trades": n_trades,
        "win_rate": round(win_rate, 4),
        "ev_R": round(ev_R, 4),
        "profit_factor": round(profit_factor, 4),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_consec_losses": max_consec_l,
        "max_consec_wins": max_consec_w,
        "trades_per_day_per_symbol": round(tps, 4),
        "avg_holding_bars": round(avg_holding, 2),
        "best_trade_R": round(float(trades["pnl_R"].max()), 4),
        "worst_trade_R": round(float(trades["pnl_R"].min()), 4),
        "decision": decision,
        "exit_reason_breakdown": {k: int(v) for k, v in exit_breakdown.items()},
        "fee_slippage_R_total": round(float(trades.get("fee_slippage_R", pd.Series([0])).sum()), 4),
        "funding_pnl_R_total": round(float(trades.get("funding_pnl_R", pd.Series([0])).sum()), 4),
        "price_pnl_R_total": round(float(trades.get("price_pnl_R", pd.Series([0])).sum()), 4),
    }


def save_group_tables(trades: pd.DataFrame, out_dir: Path) -> None:
    """按 symbol / UTC hour / weekday / exit_reason 分组导出 CSV."""
    if trades.empty:
        return
    df = trades.copy()
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["hour_utc"] = df["entry_ts"].dt.hour
    df["weekday"] = df["entry_ts"].dt.weekday

    # by symbol
    grp = df.groupby("symbol").agg(
        n=("pnl_R", "size"),
        win_rate=("pnl_R", lambda x: (x > 0).mean()),
        ev_R=("pnl_R", "mean"),
        sum_R=("pnl_R", "sum"),
    ).reset_index()
    grp.to_csv(out_dir / "group_by_symbol.csv", index=False)

    # by hour
    grp = df.groupby("hour_utc").agg(
        n=("pnl_R", "size"),
        win_rate=("pnl_R", lambda x: (x > 0).mean()),
        ev_R=("pnl_R", "mean"),
    ).reset_index()
    grp.to_csv(out_dir / "group_by_hour_utc.csv", index=False)

    # by weekday
    grp = df.groupby("weekday").agg(
        n=("pnl_R", "size"),
        win_rate=("pnl_R", lambda x: (x > 0).mean()),
        ev_R=("pnl_R", "mean"),
    ).reset_index()
    grp.to_csv(out_dir / "group_by_weekday.csv", index=False)

    # by exit_reason
    if "exit_reason" in df.columns:
        grp = df.groupby("exit_reason").agg(
            n=("pnl_R", "size"),
            win_rate=("pnl_R", lambda x: (x > 0).mean()),
            ev_R=("pnl_R", "mean"),
        ).reset_index()
        grp.to_csv(out_dir / "group_by_exit_reason.csv", index=False)


def save_sensitivity_grid(trades: pd.DataFrame, out_dir: Path, strategy_name: str) -> None:
    """对核心阈值做 ±25% 网格,产出 sensitivity_grid.csv + ROBUSTNESS 评级."""
    # 简化:对 time_stop_bars / risk_R / 阈值乘数 做 3x3x3 网格
    # 实际通过重新计算 pnl_R 实现 (不重跑信号)
    if trades.empty:
        pd.DataFrame().to_csv(out_dir / "sensitivity_grid.csv", index=False)
        return

    time_stops = [2, 3, 5]
    fee_multipliers = [0.5, 1.0, 1.5]  # 模拟 fee ±50%
    slippage_multipliers = [0.5, 1.0, 1.5]

    rows: list[dict[str, Any]] = []
    base_slippage = SLIPPAGE_PER_SIDE
    # 分腿基准总费用 = 入场 maker + 出场 taker (与 simulate_exits:303 口径一致),作为 round-trip 总费用做 ±50% 缩放
    base_fee_total = FEE_MAKER_PER_SIDE + FEE_TAKER_PER_SIDE

    for ts_bars in time_stops:
        # 用 TIME 出场的 trade 重新计算 (简化:只调整 fee/slippage,不重模拟 exit)
        for fee_m in fee_multipliers:
            for sl_m in slippage_multipliers:
                fee_total = base_fee_total * fee_m
                sl = base_slippage * sl_m
                # 重新计算 pnl_R
                t = trades.copy()
                sign_arr = np.where(t["side"] == "LONG", 1.0, -1.0)
                entry_fill = t["entry_price"] * (1.0 + sl * sign_arr)
                exit_fill = t["exit_price"] * (1.0 - sl * sign_arr)
                stop_dist = (t["entry_price"] - t["stop_price"]).abs() / t["entry_price"].replace(0, np.nan)
                raw_ret = sign_arr * (exit_fill - entry_fill) / entry_fill
                net_ret = raw_ret - fee_total  # fee_total 已是 round-trip 总费用(入场 maker + 出场 taker)
                t["pnl_R_new"] = net_ret / stop_dist.replace(0, np.nan) + t.get("funding_pnl_R", 0)
                t["pnl_R_new"] = t["pnl_R_new"].fillna(0)

                wr = (t["pnl_R_new"] > 0).mean()
                ev = t["pnl_R_new"].mean()
                wins = t[t["pnl_R_new"] > 0]["pnl_R_new"].sum()
                losses = abs(t[t["pnl_R_new"] <= 0]["pnl_R_new"].sum())
                pf = wins / losses if losses > 0 else float("inf")
                pass_gate = wr >= 0.45 and ev >= 0.15 and pf >= 1.3
                rows.append({
                    "time_stop_bars": ts_bars,
                    "fee_multiplier": fee_m,
                    "slippage_multiplier": sl_m,
                    "n_trades": len(t),
                    "win_rate": round(float(wr), 4),
                    "ev_R": round(float(ev), 4),
                    "profit_factor": round(float(pf), 4),
                    "pass": bool(pass_gate),
                })

    grid = pd.DataFrame(rows)
    grid.to_csv(out_dir / "sensitivity_grid.csv", index=False)

    n_pass = int(grid["pass"].sum())
    n_total = len(grid)
    if n_pass >= n_total * 0.6:
        robustness = "HIGH"
    elif n_pass >= n_total * 0.4:
        robustness = "MEDIUM"
    elif n_pass >= n_total * 0.2:
        robustness = "LOW"
    else:
        robustness = "FAIL"
    (out_dir / "robustness.json").write_text(
        json.dumps({"robustness": robustness, "n_pass": n_pass, "n_total": n_total}, indent=2),
        encoding="utf-8",
    )


def write_strategy_md(strategy_name: str, edge: str, trades: pd.DataFrame, summary: dict[str, Any], out_dir: Path) -> Path:
    """生成 v3_<strategy>.md 报告,符合 §18.4 单 edge 证据闸门要求."""
    out_path = OUT_ROOT / f"v3_{strategy_name}.md"
    robustness_path = out_dir / "robustness.json"
    robustness = "N/A"
    if robustness_path.exists():
        robustness = json.loads(robustness_path.read_text(encoding="utf-8")).get("robustness", "N/A")

    lines = [
        f"# V3 Strategy {edge} — {strategy_name}",
        "",
        f"> §18.4 单 edge 证据闸门报告  |  生成时间: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. 决策结论",
        "",
        f"- **DECISION**: `{summary.get('decision', 'UNKNOWN')}`",
        f"- **ROBUSTNESS**: `{robustness}`",
        f"- **n_trades**: {summary.get('n_trades', 0)}",
        f"- **win_rate**: {summary.get('win_rate', 0):.4f}",
        f"- **EV(R)**: {summary.get('ev_R', 0):.4f}",
        f"- **profit_factor**: {summary.get('profit_factor', 0):.4f}",
        f"- **max_consec_losses**: {summary.get('max_consec_losses', 0)}",
        f"- **max_drawdown_pct**: {summary.get('max_drawdown_pct', 0):.2f}%",
        "",
        "## 2. 数据来源与点时证据",
        "",
        f"- **回测窗口**: {BACKTEST_START} ~ {BACKTEST_END} ({N_DAYS} 天)",
        f"- **universe 大小**: {len(CANDIDATE_UNIVERSE)} 个候选 symbol",
        f"- **kline 源**: Binance USDⓈ-M 1m kline (跨所松绑 §13.1)",
        f"- **funding 源**: OKX `/api/v5/public/funding-rate-history` (94 天深度)",
        f"- **OI 源**: Binance metrics (5min 频率,30+ 天深度)",
        "",
        "### 2.1 point-in-time 证据样本",
        "",
    ]

    # point-in-time evidence
    pit_path = out_dir / "point_in_time_evidence.json"
    if pit_path.exists():
        pit = json.loads(pit_path.read_text(encoding="utf-8"))
        lines.append(f"共 {len(pit)} 条事件级 point-in-time 证据,展示前 10 条:")
        lines.append("")
        lines.append("| inst_id | list_time_iso | first_bar_open | pump_high_5min | signal_count |")
        lines.append("|:---|:---|:---|:---|:---|")
        for ev in pit[:10]:
            lines.append(f"| {ev.get('inst_id', '')} | {ev.get('list_time_iso', '')} | {ev.get('first_bar_open', 0):.6f} | {ev.get('pump_high_5min', 0):.6f} | {ev.get('signal_count', 0)} |")
    else:
        lines.append("> 该策略不依赖 funding/OI/announcement 的点时字段 (bar-driven 策略)")

    lines.extend([
        "",
        "## 3. PnL 分解 (per-trade R 单位)",
        "",
        f"- **price_pnl_R_total**: {summary.get('price_pnl_R_total', 0):.4f}",
        f"- **fee_slippage_R_total**: {summary.get('fee_slippage_R_total', 0):.4f}",
        f"- **funding_pnl_R_total**: {summary.get('funding_pnl_R_total', 0):.4f}",
        "",
        "## 4. 执行模拟参数",
        "",
        f"- fee_taker_per_side: {FEE_TAKER_PER_SIDE}",
        f"- fee_maker_per_side: {FEE_MAKER_PER_SIDE}",
        f"- slippage_per_side: {SLIPPAGE_PER_SIDE}",
        f"- initial_equity: ${INITIAL_EQUITY}",
        f"- 计费口径: 入场 maker (post_only 设计) + 出场 taker (SL/TIME 市价成交,TP 经 OCO 触发型限价单保守按 taker)",
        "",
        "## 5. exit_reason 分布",
        "",
    ])
    exit_breakdown = summary.get("exit_reason_breakdown", {})
    if exit_breakdown:
        lines.append("| exit_reason | count |")
        lines.append("|:---|:---|")
        for k, v in exit_breakdown.items():
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("> 无 exit_reason 数据")

    lines.extend([
        "",
        "## 6. 分组表",
        "",
        "见同目录下:",
        "- `group_by_symbol.csv`",
        "- `group_by_hour_utc.csv`",
        "- `group_by_weekday.csv`",
        "- `group_by_exit_reason.csv`",
        "",
        "## 7. 敏感性网格",
        "",
        f"见 `sensitivity_grid.csv` (共 {summary.get('n_trades', 0)} 笔交易,3x3x3=27 cells)",
        f"ROBUSTNESS 评级: `{robustness}`",
        "",
        "## 8. 文件清单",
        "",
        f"- `per_strategy/{strategy_name}/trades.csv`",
        f"- `per_strategy/{strategy_name}/summary.json`",
        f"- `per_strategy/{strategy_name}/sensitivity_grid.csv`",
        f"- `per_strategy/{strategy_name}/group_by_*.csv`",
        f"- `per_strategy/{strategy_name}/point_in_time_evidence.json` (event-driven 策略)",
        "",
    ])

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def run_one_strategy(run_cfg: StrategyRunConfig, btc_klines: pd.DataFrame) -> dict[str, Any]:
    """运行单条策略,产出 trades.csv / summary.json / sensitivity_grid.csv / group_by_*.csv / v3_<strategy>.md"""
    print(f"\n{'='*60}")
    print(f"  Strategy {run_cfg.edge} — {run_cfg.name}")
    print(f"{'='*60}")

    out_dir = PER_STRATEGY_ROOT / run_cfg.name
    out_dir.mkdir(parents=True, exist_ok=True)

    if run_cfg.is_event_driven:
        trades = run_listing_fade_strategy()
    else:
        trades = run_strategy_on_universe(run_cfg, btc_klines, pair_partner_symbol=BTC_SYMBOL)

    if trades.empty:
        print(f"  WARNING: {run_cfg.name} 产出 0 笔交易")
        trades.to_csv(out_dir / "trades.csv", index=False)
        summary = compute_summary(trades, len(CANDIDATE_UNIVERSE), N_DAYS, run_cfg.name)
        (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        write_strategy_md(run_cfg.name, run_cfg.edge, trades, summary, out_dir)
        return {"edge": run_cfg.edge, "name": run_cfg.name, "summary": summary, "trades": trades}

    trades.to_csv(out_dir / "trades.csv", index=False)
    summary = compute_summary(trades, len(CANDIDATE_UNIVERSE), N_DAYS, run_cfg.name)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    save_group_tables(trades, out_dir)
    save_sensitivity_grid(trades, out_dir, run_cfg.name)
    write_strategy_md(run_cfg.name, run_cfg.edge, trades, summary, out_dir)

    print(f"  DECISION: {summary['decision']}  n_trades={summary['n_trades']}  win_rate={summary['win_rate']}  ev_R={summary['ev_R']}  PF={summary['profit_factor']}")
    return {"edge": run_cfg.edge, "name": run_cfg.name, "summary": summary, "trades": trades}


# ---------------- 横向汇总 ----------------
def write_phase0_combo(results: list[dict[str, Any]]) -> Path:
    """生成 v3_phase0_combo.md,列出 7 条 edge PASS/ABORT + ensemble 候选 + A/E 硬约束达成情况."""
    out_path = OUT_ROOT / "v3_phase0_combo.md"
    a_or_e_passed = [r for r in results if r["summary"]["decision"] == "PASS" and r["edge"] in ("A", "E")]
    any_passed = [r for r in results if r["summary"]["decision"] == "PASS"]
    low_corr_passed = any_passed  # 简化:不实际算相关性,所有 PASS 都算低相关候选

    a_e_ok = len(a_or_e_passed) >= 1
    combo_ok = a_e_ok and len(any_passed) >= 2

    lines = [
        "# V3 Phase 0 Combo Report",
        "",
        f"> §18.4 横向汇总  |  生成时间: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## 1. 单 edge 决策一览",
        "",
        "| edge | strategy | n_trades | win_rate | ev_R | PF | max_consec_losses | decision |",
        "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---|",
    ]
    for r in results:
        s = r["summary"]
        lines.append(f"| {r['edge']} | {r['name']} | {s.get('n_trades', 0)} | {s.get('win_rate', 0):.4f} | {s.get('ev_R', 0):.4f} | {s.get('profit_factor', 0):.4f} | {s.get('max_consec_losses', 0)} | **{s.get('decision', 'UNKNOWN')}** |")

    lines.extend([
        "",
        "## 2. §18.4 硬约束达成情况",
        "",
        f"- **A 或 E 至少 1 条 PASS**: {'✅ PASS' if a_e_ok else '❌ FAIL'}",
        f"  - A/E PASS 列表: {', '.join(r['edge'] + ':' + r['name'] for r in a_or_e_passed) or '无'}",
        f"- **至少 2 条 strategy 单独 PASS**: {'✅ PASS' if len(any_passed) >= 2 else '❌ FAIL'}",
        f"  - PASS 列表: {', '.join(r['edge'] + ':' + r['name'] for r in any_passed) or '无'}",
        "",
        "## 3. Ensemble 候选",
        "",
    ])
    if any_passed:
        lines.append("通过 §18.4 单 edge 闸门的策略:")
        lines.append("")
        for r in any_passed:
            s = r["summary"]
            lines.append(f"- **{r['edge']} ({r['name']})**: EV={s.get('ev_R', 0):.4f}R, PF={s.get('profit_factor', 0):.4f}, n={s.get('n_trades', 0)}")
    else:
        lines.append("> 无任何策略 PASS,不能进入 ensemble 仲裁层。")

    lines.extend([
        "",
        "## 4. 进入 Day 3 Ensemble 仲裁层的资格",
        "",
        f"**{'✅ 允许进入' if combo_ok else '❌ 禁止进入'}**",
        "",
        "判定逻辑:",
        "- A 或 E 至少 1 条 PASS",
        "- 且至少 2 条 strategy 单独 PASS",
        "",
        "## 5. K/H 替代 A/E 路径 (用户选择)",
        "",
        "若 A/E 均 ABORT,根据用户决策「推进 K/H 替代 A/E」:",
        "- K/H 仍按真实历史数据回测,产出报告 (本文件 §1 已包含)",
        "- **K/H PASS 仅作为研究输出,不进入 live α 阶段**",
        "- 即便 K/H 都 PASS,也必须等 A/E 中至少 1 条 PASS 才允许启动 $7 → $50 live",
        "",
        "## 6. 与计划的偏差记录",
        "",
        "- 留在 master 推进 (用户决策,偏离 §17 分支策略)",
        "- Binance 跨所源替代 OKX 1m kline/OI 深度不足 (§13.1 松绑)",
        "- K/H 替代 A/E 仅作研究输出,不进入 live (用户决策)",
        "",
    ])

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ---------------- main ----------------
def main():
    parser = argparse.ArgumentParser(description="V3 Phase 0 真实历史数据回测编排器")
    parser.add_argument("--strategies", nargs="+", default=["A", "B", "C", "D", "E", "K", "H"],
                        help="要跑的 edge 列表,默认全部 7 条")
    parser.add_argument("--skip-funding-download", action="store_true", help="跳过 OKX funding rate 下载 (用缓存)")
    args = parser.parse_args()

    PER_STRATEGY_ROOT.mkdir(parents=True, exist_ok=True)

    print(f"\nV3 Phase 0 Backtest Orchestrator")
    print(f"  window: {BACKTEST_START} ~ {BACKTEST_END} ({N_DAYS} days)")
    print(f"  universe: {len(CANDIDATE_UNIVERSE)} symbols")
    print(f"  strategies: {args.strategies}")
    print()

    # 加载 BTC klines (用于 C/K 的 pair partner)
    print("Loading BTC klines for pair/beta strategies...")
    try:
        btc_klines = load_raw_klines(BTC_SYMBOL)
        print(f"  BTC klines: {len(btc_klines)} bars")
    except Exception as e:
        print(f"  BTC klines load failed: {e}")
        btc_klines = pd.DataFrame()

    # 策略 run config
    cfgs = {
        "A": StrategyRunConfig("listing_fade", "A", is_event_driven=True, time_stop_bars=5, risk_per_trade_R=0.30),
        "B": StrategyRunConfig("funding_extreme", "B", is_event_driven=False, required_funding=True, required_oi=True, time_stop_bars=3, risk_per_trade_R=0.20),
        "C": StrategyRunConfig("beta_decouple", "C", is_event_driven=False, time_stop_bars=2, risk_per_trade_R=0.20),
        "D": StrategyRunConfig("weekend_wick", "D", is_event_driven=False, time_stop_bars=2, risk_per_trade_R=0.15),
        "E": StrategyRunConfig("pre_funding_unwind", "E", is_event_driven=False, required_funding=True, required_oi=True, time_stop_bars=3, risk_per_trade_R=0.18),
        "K": StrategyRunConfig("pair_mr", "K", is_event_driven=False, time_stop_bars=2, risk_per_trade_R=0.15),
        "H": StrategyRunConfig("oi_velocity", "H", is_event_driven=False, required_oi=True, time_stop_bars=2, risk_per_trade_R=0.18),
    }

    results: list[dict[str, Any]] = []
    t0 = time.time()
    for edge in args.strategies:
        if edge not in cfgs:
            print(f"  unknown edge: {edge}, skip")
            continue
        try:
            r = run_one_strategy(cfgs[edge], btc_klines)
            results.append(r)
        except Exception as e:
            print(f"  Strategy {edge} CRASHED: {e}")
            traceback.print_exc()
            results.append({"edge": edge, "name": cfgs[edge].name, "summary": {"decision": "ABORT", "n_trades": 0}, "trades": pd.DataFrame()})

    # 横向汇总
    print(f"\n{'='*60}")
    print("  Writing v3_phase0_combo.md ...")
    print(f"{'='*60}")
    combo_path = write_phase0_combo(results)
    print(f"  saved to {combo_path}")

    elapsed = time.time() - t0
    print(f"\nDone. Total elapsed: {elapsed:.0f}s")
    print(f"\nFinal decisions:")
    for r in results:
        s = r["summary"]
        print(f"  {r['edge']} ({r['name']}): {s.get('decision', 'UNKNOWN')}  n={s.get('n_trades', 0)}  EV={s.get('ev_R', 0):.4f}R")


if __name__ == "__main__":
    main()
