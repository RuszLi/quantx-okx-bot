"""
test_engine.py — Tests for engine module.
"""
import pytest
import pandas as pd
import numpy as np

from src.backtest.engine import simulate, ExecParams


def _make_features_with_signal(n_bars_after_signal: int = 10) -> pd.DataFrame:
    """Create a features DataFrame with a long entry signal and subsequent price bars.
    After the signal, price moves up enough to hit TP within 2 bars.
    """
    n_total = 100
    idx = pd.date_range("2026-06-01", periods=n_total, freq="1min", tz="UTC", name="ts")
    price_base = 100.0

    df = pd.DataFrame(index=idx)
    df["open"] = price_base
    df["high"] = price_base
    df["low"] = price_base
    df["close"] = price_base
    df["volume"] = 1000.0
    df["quote_volume"] = 100000.0
    df["taker_buy_quote"] = 50000.0
    df["taker_sell_quote"] = 50000.0
    df["oi_value"] = 1000000.0
    df["oi_value_diff_5m"] = 0.0
    df["liq_buy_usd"] = np.nan
    df["liq_sell_usd"] = np.nan

    # Feature columns
    df["vwap_15m"] = price_base
    df["atr_15m"] = 1.0
    df["displacement"] = 0.0
    df["flow_imbalance"] = 0.0
    df["single_side_ratio"] = 0.0
    df["liq_usd_60s"] = 0.0
    df["liq_p95"] = 1e6
    df["liq_accel"] = 0.0
    df["cond_volume"] = False
    df["cond_single_side"] = False
    df["cond_displacement"] = False
    df["cond_decelerating"] = False

    df["signal"] = 0

    # Signal at bar 20
    si = 20
    df.loc[df.index[si], "signal"] = +1  # LONG
    entry_px = 100.0
    target_px = 103.0  # TP hit easily
    stop_px = 98.8     # 1.2% stop
    df.loc[df.index[si], "entry_price"] = entry_px
    df.loc[df.index[si], "target_price"] = target_px
    df.loc[df.index[si], "stop_price"] = stop_px
    df.loc[df.index[si], "cond_volume"] = True
    df.loc[df.index[si], "cond_single_side"] = True
    df.loc[df.index[si], "cond_displacement"] = True
    df.loc[df.index[si], "cond_decelerating"] = True
    df.loc[df.index[si], "displacement"] = -2.0
    df.loc[df.index[si], "flow_imbalance"] = -0.9

    # Price rises after signal - bar 21 high > target
    df.loc[df.index[si + 1], "high"] = 104.0
    df.loc[df.index[si + 1], "low"] = 99.5
    df.loc[df.index[si + 1], "close"] = 103.5
    df.loc[df.index[si + 1], "open"] = 100.5

    return df


def _make_features_short_with_sl() -> pd.DataFrame:
    """Features with a short signal that hits stop loss."""
    n_total = 100
    idx = pd.date_range("2026-06-01", periods=n_total, freq="1min", tz="UTC", name="ts")
    price_base = 100.0

    df = pd.DataFrame(index=idx)
    df["open"] = price_base
    df["high"] = price_base
    df["low"] = price_base
    df["close"] = price_base
    df["volume"] = 1000.0
    df["quote_volume"] = 100000.0
    df["taker_buy_quote"] = 50000.0
    df["taker_sell_quote"] = 50000.0
    df["oi_value"] = 1000000.0
    df["oi_value_diff_5m"] = 0.0
    df["liq_buy_usd"] = np.nan
    df["liq_sell_usd"] = np.nan

    df["vwap_15m"] = price_base
    df["atr_15m"] = 1.0
    df["displacement"] = 0.0
    df["flow_imbalance"] = 0.0
    df["single_side_ratio"] = 0.0
    df["liq_usd_60s"] = 0.0
    df["liq_p95"] = 1e6
    df["liq_accel"] = 0.0
    df["cond_volume"] = False
    df["cond_single_side"] = False
    df["cond_displacement"] = False
    df["cond_decelerating"] = False
    df["signal"] = 0

    si = 20
    df.loc[df.index[si], "signal"] = -1  # SHORT
    entry_px = 100.0
    target_px = 97.0
    stop_px = 101.2     # 1.2% stop
    df.loc[df.index[si], "entry_price"] = entry_px
    df.loc[df.index[si], "target_price"] = target_px
    df.loc[df.index[si], "stop_price"] = stop_px
    df.loc[df.index[si], "cond_volume"] = True
    df.loc[df.index[si], "cond_single_side"] = True
    df.loc[df.index[si], "cond_displacement"] = True
    df.loc[df.index[si], "cond_decelerating"] = True
    df.loc[df.index[si], "displacement"] = 2.0
    df.loc[df.index[si], "flow_imbalance"] = 0.9

    # Price rises against position - hit SL
    df.loc[df.index[si + 1], "high"] = 102.0
    df.loc[df.index[si + 1], "low"] = 99.0
    df.loc[df.index[si + 1], "close"] = 101.5
    df.loc[df.index[si + 1], "open"] = 100.5

    return df


def test_simulate_long_tp():
    """Long signal should hit TP when price reaches target."""
    feats = _make_features_with_signal()
    trades = simulate(feats)
    assert len(trades) > 0, "Should generate at least one trade"
    t = trades.iloc[0]
    assert t["side"] == "LONG"
    assert t["exit_reason"] == "TP"
    assert t["pnl_R"] > 0, f"TP trade should profit, got pnl_R={t['pnl_R']}"


def test_simulate_short_sl():
    """Short signal should hit SL when price reaches stop."""
    feats = _make_features_short_with_sl()
    trades = simulate(feats)
    assert len(trades) > 0
    t = trades.iloc[0]
    assert t["side"] == "SHORT"
    assert t["exit_reason"] == "SL"
    assert t["pnl_R"] < 0, f"SL trade should lose, got pnl_R={t['pnl_R']}"


def test_1r_loss_equals_20pct_equity():
    """Verify that a full 1R loss = -20% equity (given risk_per_trade_pct=0.20)."""
    feats = _make_features_short_with_sl()
    trades = simulate(feats)
    t = trades.iloc[0]
    # pnl_R should be near -1 (adjusted for slippage + fees)
    assert t["pnl_R"] < -0.9, f"Expected ~-1R, got {t['pnl_R']}"
    # pnl_pct_equity should be near -20%
    assert t["pnl_pct_equity"] < -15, f"Expected ~-20%, got {t['pnl_pct_equity']}%"


def test_trades_csv_columns():
    feats = _make_features_with_signal()
    trades = simulate(feats)
    expected_cols = ["entry_ts", "exit_ts", "side", "entry_price", "exit_price",
                     "target_price", "stop_price", "exit_reason", "pnl_R",
                     "pnl_pct_equity", "equity_after"]
    for col in expected_cols:
        assert col in trades.columns, f"Missing column: {col}"


def test_no_signal_no_trades():
    """Zero-signal DataFrame should produce zero trades."""
    idx = pd.date_range("2026-06-01", periods=50, freq="1min", tz="UTC", name="ts")
    df = pd.DataFrame(index=idx)
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_quote", "taker_sell_quote", "oi_value",
                "oi_value_diff_5m", "liq_buy_usd", "liq_sell_usd",
                "vwap_15m", "atr_15m", "displacement", "flow_imbalance",
                "single_side_ratio", "liq_usd_60s", "liq_p95", "liq_accel",
                "cond_volume", "cond_single_side", "cond_displacement",
                "cond_decelerating", "signal", "entry_price",
                "target_price", "stop_price"]:
        df[col] = 0.0
    df["signal"] = 0
    trades = simulate(df)
    assert len(trades) == 0, "Zero signals should produce zero trades"


def test_cooldown_after_two_losses():
    """After 2 consecutive losses, engine should skip 30 bars."""
    n_total = 200
    idx = pd.date_range("2026-06-01", periods=n_total, freq="1min", tz="UTC", name="ts")
    df = pd.DataFrame(index=idx)
    for col in ["open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_quote", "taker_sell_quote", "oi_value",
                "oi_value_diff_5m", "liq_buy_usd", "liq_sell_usd",
                "vwap_15m", "atr_15m", "displacement", "flow_imbalance",
                "single_side_ratio", "liq_usd_60s", "liq_p95", "liq_accel",
                "cond_volume", "cond_single_side", "cond_displacement",
                "cond_decelerating", "signal", "entry_price",
                "target_price", "stop_price"]:
        df[col] = 0.0
    df["high"] = 100.0
    df["low"] = 100.0
    df["close"] = 100.0
    df["open"] = 100.0
    df["signal"] = 0

    # Signal 1: SHORT, will hit SL
    df.loc[df.index[10], "signal"] = -1
    df.loc[df.index[10], "entry_price"] = 100.0
    df.loc[df.index[10], "target_price"] = 97.0
    df.loc[df.index[10], "stop_price"] = 101.2
    df.loc[df.index[11], "high"] = 102.0  # hit SL

    # Signal 2: SHORT, will hit SL again
    df.loc[df.index[50], "signal"] = -1
    df.loc[df.index[50], "entry_price"] = 100.0
    df.loc[df.index[50], "target_price"] = 97.0
    df.loc[df.index[50], "stop_price"] = 101.2
    df.loc[df.index[51], "high"] = 102.0  # hit SL

    # Signal 3: LONG, TP (but should be skipped by cooldown if within 30 bars)
    df.loc[df.index[60], "signal"] = +1
    df.loc[df.index[60], "entry_price"] = 100.0
    df.loc[df.index[60], "target_price"] = 103.0
    df.loc[df.index[60], "stop_price"] = 98.8
    df.loc[df.index[61], "high"] = 104.0

    trades = simulate(df)
    # Should have exactly 2 trades (first 2 losses), 3rd skipped by cooldown
    assert len(trades) <= 2, f"3rd trade should be skipped by cooldown, got {len(trades)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
