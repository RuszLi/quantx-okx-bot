import pandas as pd

from src.backtest.strategies.pair_mr import PairMRStrategy


def test_pair_mr_opens_two_leg_mean_reversion_trade():
    index = pd.date_range("2026-06-25 00:00:00", periods=6, freq="1h", tz="UTC")
    market_data = pd.DataFrame(
        {
            "price_a": [10.0, 10.1, 10.2, 10.4, 10.8, 11.5],
            "price_b": [10.0, 10.0, 10.0, 10.0, 10.1, 10.1],
            "bucket_momentum_pct": [0.2, 0.2, 0.3, 0.4, 0.45, 0.2],
            "volume_a_24h": [6e6, 6e6, 6e6, 6e6, 6e6, 6e6],
            "volume_b_24h": [6e6, 6e6, 6e6, 6e6, 6e6, 6e6],
            "pair_eligible": [True, True, True, True, True, True],
        },
        index=index,
    )

    strategy = PairMRStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    signal = signals.iloc[-1]
    assert signal["signal"] == -1
    assert signal["entry_price"] > 0
    assert signal["meta"]["leg_a"] == "SHORT"
    assert signal["meta"]["leg_b"] == "LONG"
