import pandas as pd

from src.backtest.strategies.weekend_wick import RR_MIN, WeekendWickStrategy


def test_weekend_wick_fades_spike_inside_weekend_window():
    index = pd.date_range("2026-06-27 00:00:00", periods=6, freq="1h", tz="UTC")
    market_data = pd.DataFrame(
        {
            "open": [100, 100, 100, 100, 100, 100],
            "high": [101, 102, 103, 104, 120, 108],
            "low": [99, 99, 99, 99, 98, 97],
            "close": [100, 100, 100, 100, 118, 106],
            "volume": [5e6, 5e6, 5e6, 5e6, 5e6, 5e6],
            "wick_z": [0.2, 0.3, 0.4, 0.5, 3.2, 0.8],
        },
        index=index,
    )

    strategy = WeekendWickStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    signal = signals.iloc[-1]
    assert signal["signal"] == -1
    assert signal["stop_price"] > signal["entry_price"]


def test_weekend_wick_clamps_target_to_rr_floor_when_prev_close_is_too_near() -> None:
    index = pd.date_range("2026-06-27 00:00:00", periods=2, freq="1h", tz="UTC")
    market_data = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [100.5, 102.0],
            "low": [99.5, 99.0],
            "close": [100.0, 100.1],
            "volume": [5e6, 5e6],
            "wick_z": [0.1, 3.0],
        },
        index=index,
    )

    strategy = WeekendWickStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) == 1
    signal = signals.iloc[0]
    assert signal["signal"] == -1

    target_distance = float(signal["entry_price"] - signal["target_price"])
    stop_distance = float(signal["stop_price"] - signal["entry_price"])

    assert target_distance >= (RR_MIN * stop_distance) - 1e-9
    assert signal["target_price"] < 100.0
