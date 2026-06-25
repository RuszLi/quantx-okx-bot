import pandas as pd

from src.backtest.strategies.beta_decouple import BetaDecoupleStrategy


def test_beta_decouple_fades_alt_when_btc_is_flat():
    index = pd.date_range("2026-06-25 00:00:00", periods=6, freq="1h", tz="UTC")
    market_data = pd.DataFrame(
        {
            "btc_close": [100, 100.2, 100.1, 100.0, 100.05, 100.0],
            "btc_return_60m": [0.000, 0.001, -0.001, 0.000, 0.0005, 0.0002],
            "btc_rv_pct": [0.20, 0.21, 0.19, 0.18, 0.10, 0.12],
            "alt_close": [10, 10.2, 10.5, 10.7, 11.6, 12.2],
            "alt_vwap_60m": [10, 10, 10, 10, 10, 10],
            "alt_volume_24h": [20e6, 20e6, 20e6, 20e6, 20e6, 20e6],
            "alt_age_days": [31, 31, 31, 31, 31, 31],
        },
        index=index,
    )

    strategy = BetaDecoupleStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    signal = signals.iloc[-1]
    assert signal["signal"] == -1
    assert signal["entry_price"] == market_data.iloc[-1]["alt_close"]
