import pandas as pd

from src.backtest.strategies.pre_funding_unwind import PreFundingUnwindStrategy


def test_pre_funding_unwind_requires_settlement_window_and_reversal():
    index = pd.date_range("2026-06-25 07:00:00", periods=7, freq="10min", tz="UTC")
    market_data = pd.DataFrame(
        {
            "close": [100, 102, 104, 105, 104, 103, 102],
            "high": [101, 103, 105, 106, 105, 104, 103],
            "low": [99, 101, 103, 104, 103, 102, 101],
            "funding_rate": [0.001, 0.002, 0.004, 0.01, 0.012, 0.03, 0.014],
            "oi_value": [1000, 1100, 1250, 1400, 1500, 1600, 1700],
            "quote_volume": [10000, 10000, 10000, 10000, 10000, 10000, 10000],
            "next_funding_time": [
                pd.Timestamp("2026-06-25 08:00:00Z"),
                pd.Timestamp("2026-06-25 08:00:00Z"),
                pd.Timestamp("2026-06-25 08:00:00Z"),
                pd.Timestamp("2026-06-25 08:00:00Z"),
                pd.Timestamp("2026-06-25 08:00:00Z"),
                pd.Timestamp("2026-06-25 08:00:00Z"),
                pd.Timestamp("2026-06-25 16:00:00Z"),
            ],
        },
        index=index,
    )

    strategy = PreFundingUnwindStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    signal = signals.iloc[-1]
    assert signal["signal"] == -1
    assert signal["valid_until_ts"] >= signal["entry_ts"]
