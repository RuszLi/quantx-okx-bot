import pandas as pd

from src.backtest.strategies.funding_extreme import FundingExtremeStrategy


def test_funding_extreme_fades_positive_extreme_with_oi_confirmation():
    index = pd.date_range("2026-06-25 00:00:00", periods=6, freq="1h", tz="UTC")
    market_data = pd.DataFrame(
        {
            "close": [100, 101, 102, 101, 100.5, 100],
            "high": [101, 102, 103, 102, 101, 100.5],
            "low": [99, 100, 101, 100, 99.5, 99],
            "funding_rate": [0.001, 0.002, 0.003, 0.004, 0.02, 0.05],
            "oi_value": [1000, 1010, 1020, 1100, 1400, 1500],
            "quote_volume": [10000, 10000, 10000, 10000, 10000, 10000],
        },
        index=index,
    )

    strategy = FundingExtremeStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    last_signal = signals.iloc[-1]
    assert last_signal["signal"] == -1
    assert last_signal["entry_price"] == market_data.iloc[-1]["close"]
    assert last_signal["stop_price"] > last_signal["entry_price"]
