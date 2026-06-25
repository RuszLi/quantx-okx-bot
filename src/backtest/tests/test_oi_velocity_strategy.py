import pandas as pd

from src.backtest.strategies.oi_velocity import OIVelocityStrategy


def test_oi_velocity_fades_post_burst_after_inventory_build():
    index = pd.date_range("2026-06-25 00:00:00", periods=8, freq="5min", tz="UTC")
    market_data = pd.DataFrame(
        {
            "close": [100, 100.1, 100.2, 100.15, 100.1, 103.5, 103.0, 102.6],
            "high": [100.2, 100.3, 100.4, 100.3, 100.2, 104.0, 103.3, 102.8],
            "low": [99.9, 100.0, 100.1, 100.0, 99.9, 100.0, 102.7, 102.3],
            "oi_velocity_pct": [0.40, 0.45, 0.50, 0.55, 0.60, 0.98, 0.97, 0.96],
            "price_delta_pct": [0.05, 0.04, 0.03, 0.02, 0.01, 0.10, 0.08, 0.07],
            "burst_move_pct": [0.1, 0.1, 0.1, 0.2, 0.2, 1.8, 1.4, 1.1],
            "volume_decay_pct": [0.0, 0.0, 0.0, 0.0, 0.0, 0.35, 0.4, 0.45],
            "volume_24h": [12e6, 12e6, 12e6, 12e6, 12e6, 12e6, 12e6, 12e6],
        },
        index=index,
    )

    strategy = OIVelocityStrategy()
    signals = strategy.compute_signals(market_data)

    assert len(signals) >= 1
    signal = signals.iloc[-1]
    assert signal["signal"] == -1
    assert signal["entry_price"] == market_data.iloc[-1]["close"]
    assert signal["stop_price"] > signal["entry_price"]
