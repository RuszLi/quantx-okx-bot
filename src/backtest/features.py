"""
features.py — Phase 0 backtest feature computation.
Computes 5 AND conditions, entry signals, and entry/target/stop prices
from the raw parquet produced by loader.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureParams:
    vwap_window_min: int = 15
    atr_window_min: int = 15
    liq_rolling_sec: int = 60
    liq_p_quantile: float = 0.95
    liq_lookback_hours: int = 24
    single_side_threshold: float = 0.80
    displacement_min_atr: float = 1.5
    warmup_min_bars: int = 24 * 60


def compute_features(raw: pd.DataFrame, params: FeatureParams | None = None) -> pd.DataFrame:
    if params is None:
        params = FeatureParams()

    df = raw.copy()

    # ---- VWAP 15m ----
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    pv = typical * df["volume"].fillna(0)
    cum_pv = pv.rolling(params.vwap_window_min, min_periods=1).sum()
    cum_vol = df["volume"].fillna(0).rolling(params.vwap_window_min, min_periods=1).sum()
    df["vwap_15m"] = cum_pv / cum_vol.replace(0, np.nan)

    # ---- ATR 15m (Wilder) ----
    h = df["high"]
    l = df["low"]
    c_prev = df["close"].shift(1)
    tr = pd.concat([
        (h - l).abs(),
        (h - c_prev).abs(),
        (l - c_prev).abs(),
    ], axis=1).max(axis=1)
    df["atr_15m"] = tr.ewm(alpha=1.0 / params.atr_window_min, min_periods=params.atr_window_min).mean()

    # ---- Displacement ----
    df["displacement"] = (df["close"] - df["vwap_15m"]) / df["atr_15m"].replace(0, np.nan)

    # ---- Flow Imbalance ----
    # roll(60s) at 1-min bars = 1 bar window (60s == 1 bar), not 60 bars
    flow_roll_bars = max(1, params.liq_rolling_sec // 60)
    df["flow_imbalance"] = np.where(
        df["quote_volume"].fillna(0) > 0,
        (df["taker_buy_quote"] - df["taker_sell_quote"]) / df["quote_volume"],
        0.0,
    )
    df["flow_imbalance"] = df["flow_imbalance"].rolling(flow_roll_bars, min_periods=1).mean()
    df["single_side_ratio"] = df["flow_imbalance"].abs()

    # ---- Liquidation USD 60s rolling ----
    liq_total = df["liq_buy_usd"].fillna(0.0) + df["liq_sell_usd"].fillna(0.0)

    # OI proxy path if liquidation data is all NaN
    if liq_total.sum() == 0.0 or df["liq_buy_usd"].isna().all():
        oi_drop = (-df["oi_value_diff_5m"].fillna(0.0)).clip(lower=0)
        oi_drop_per_min = oi_drop / 5.0
        liq_total = oi_drop_per_min
        _liq_source = "OI_PROXY"
    else:
        _liq_source = "REAL"

    df["liq_usd_60s"] = liq_total.rolling(params.liq_rolling_sec, min_periods=10).sum()
    df["liq_p95"] = df["liq_usd_60s"].rolling(params.liq_lookback_hours * 60, min_periods=params.liq_lookback_hours * 60).quantile(params.liq_p_quantile)

    # ---- Liquidation Acceleration (2nd derivative) ----
    df["liq_accel"] = df["liq_usd_60s"].diff().diff()

    # ---- Conditions ----
    df["cond_volume"] = df["liq_usd_60s"] > df["liq_p95"]
    df["cond_single_side"] = df["single_side_ratio"] > params.single_side_threshold
    df["cond_displacement"] = df["displacement"].abs() > params.displacement_min_atr
    df["cond_decelerating"] = df["liq_accel"] < 0

    # ---- Signal ----
    df["signal"] = 0
    all_cond = df["cond_volume"] & df["cond_single_side"] & df["cond_displacement"] & df["cond_decelerating"]

    # Long: fade sell cascade (displacement < 0, flow < 0)
    long_mask = all_cond & (df["displacement"] < -params.displacement_min_atr) & (df["flow_imbalance"] < 0)
    df.loc[long_mask, "signal"] = +1

    # Short: fade buy cascade (displacement > 0, flow > 0)
    short_mask = all_cond & (df["displacement"] > params.displacement_min_atr) & (df["flow_imbalance"] > 0)
    df.loc[short_mask, "signal"] = -1

    # ---- Entry/Target/Stop (lookahead-safe: use next bar open) ----
    df["entry_price"] = df["open"].shift(-1)
    df["target_price"] = np.nan
    df["stop_price"] = np.nan

    vwap_shifted = df["vwap_15m"].shift(-1)
    entry_shifted = df["entry_price"]

    # For long signals: target is halfway back to VWAP
    long_idx = df["signal"] == +1
    df.loc[long_idx, "target_price"] = entry_shifted[long_idx] + 0.5 * (df.loc[long_idx, "vwap_15m"].shift(-1) - entry_shifted[long_idx])
    df.loc[long_idx, "target_price"] = df.loc[long_idx, "target_price"].fillna(entry_shifted[long_idx] * 1.03)
    df.loc[long_idx, "stop_price"] = entry_shifted[long_idx] * (1.0 - 0.012)

    # For short signals: target is halfway back to VWAP
    short_idx = df["signal"] == -1
    df.loc[short_idx, "target_price"] = entry_shifted[short_idx] + 0.5 * (df.loc[short_idx, "vwap_15m"].shift(-1) - entry_shifted[short_idx])
    df.loc[short_idx, "target_price"] = df.loc[short_idx, "target_price"].fillna(entry_shifted[short_idx] * 0.97)
    df.loc[short_idx, "stop_price"] = entry_shifted[short_idx] * (1.0 + 0.012)

    # Store liquidation data source for reporting
    df.attrs["liq_source"] = _liq_source

    return df
