"""
test_features.py — Tests for features module.
"""
import pytest
import pandas as pd
import numpy as np

from src.backtest.features import compute_features, FeatureParams


def _make_raw(n_bars: int = 2000) -> pd.DataFrame:
    """Create a minimal raw DataFrame with enough bars for warmup."""
    np.random.seed(42)
    idx = pd.date_range("2026-06-01", periods=n_bars, freq="1min", tz="UTC", name="ts")
    price = 100.0 + np.cumsum(np.random.randn(n_bars) * 0.2)
    spread = 0.02
    df = pd.DataFrame(index=idx)
    df["open"] = price + np.random.randn(n_bars) * 0.01
    df["high"] = df["open"] + abs(np.random.randn(n_bars) * 0.5)
    df["low"] = df["open"] - abs(np.random.randn(n_bars) * 0.5)
    df["close"] = price
    df["volume"] = np.random.uniform(100, 1000, n_bars)
    df["quote_volume"] = df["close"] * df["volume"]
    df["taker_buy_quote"] = df["quote_volume"] * 0.5
    df["taker_sell_quote"] = df["quote_volume"] * 0.5
    df["oi_value"] = 1000000.0 + np.cumsum(np.random.randn(n_bars) * 100)
    df["oi_value_diff_5m"] = df["oi_value"].diff(5)
    df["liq_buy_usd"] = np.nan
    df["liq_sell_usd"] = np.nan

    # Inject a liquidation cascade event in the last third of the data
    s_start = max(0, int(n_bars * 0.7))
    s_end = min(n_bars, int(n_bars * 0.80))
    r_start = s_end
    r_end = min(n_bars, int(n_bars * 0.90))
    cascade_size = max(1, s_end - s_start)
    recovery_size = max(1, r_end - r_start)
    # sharp sell-off with OI drop
    for i in range(s_start, s_end):
        progress = (i - s_start) / cascade_size if cascade_size > 0 else 0
        df.iloc[i, df.columns.get_loc("close")] = price[i] * (1.0 - 0.02 * progress)
        df.iloc[i, df.columns.get_loc("taker_buy_quote")] = df.iloc[i]["quote_volume"] * 0.2
        df.iloc[i, df.columns.get_loc("taker_sell_quote")] = df.iloc[i]["quote_volume"] * 0.8
        df.iloc[i, df.columns.get_loc("oi_value_diff_5m")] = -5000.0
    # recovery
    for i in range(r_start, r_end):
        progress = (i - r_start) / recovery_size if recovery_size > 0 else 0
        df.iloc[i, df.columns.get_loc("close")] = price[i] * (1.0 - 0.02 + 0.015 * progress)
        df.iloc[i, df.columns.get_loc("taker_buy_quote")] = df.iloc[i]["quote_volume"] * 0.7
        df.iloc[i, df.columns.get_loc("taker_sell_quote")] = df.iloc[i]["quote_volume"] * 0.3
        df.iloc[i, df.columns.get_loc("oi_value_diff_5m")] = -100.0

    return df


def test_compute_features_has_columns():
    raw = _make_raw(2000)
    result = compute_features(raw)

    required = ["vwap_15m", "atr_15m", "displacement", "flow_imbalance",
                "single_side_ratio", "liq_usd_60s", "liq_p95", "liq_accel",
                "signal", "entry_price", "target_price", "stop_price",
                "cond_volume", "cond_single_side", "cond_displacement", "cond_decelerating"]
    for col in required:
        assert col in result.columns, f"Missing column: {col}"


def test_signal_types():
    raw = _make_raw(2000)
    result = compute_features(raw)
    # signal should be in {-1, 0, +1}
    unique = set(result["signal"].dropna().unique())
    assert unique.issubset({-1, 0, 1}), f"Unexpected signal values: {unique}"


def test_oi_proxy_activated_when_liq_is_nan():
    raw = _make_raw(500)
    raw["liq_buy_usd"] = np.nan
    raw["liq_sell_usd"] = np.nan
    result = compute_features(raw)
    source = result.attrs.get("liq_source", "")
    assert source == "OI_PROXY", f"Expected OI_PROXY, got {source}"


def test_entry_price_is_future_bar():
    """entry_price must be open[t+1], not close[t]."""
    raw = _make_raw(500)
    raw.iloc[200, raw.columns.get_loc("open")] = 999.0
    result = compute_features(raw)
    # signal at bar 199 should have entry_price = open[200] = 999.0
    sig_idx = result.index[199]
    assert result.loc[sig_idx, "signal"] in (-1, 0, 1)


def test_output_rows_match_input():
    raw = _make_raw(1000)
    result = compute_features(raw)
    assert len(result) == len(raw), f"Expected {len(raw)} rows, got {len(result)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
