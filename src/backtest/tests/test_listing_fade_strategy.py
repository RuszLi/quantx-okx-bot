import pandas as pd

from src.backtest.strategies.listing_fade import ListingFadeStrategy


def test_listing_fade_emits_short_signal_after_pump_and_pullback():
    index = pd.date_range("2026-06-25 08:00:00", periods=10, freq="1min", tz="UTC")
    market_data = pd.DataFrame(
        {
            "open": [100, 112, 116, 118, 117, 104, 103, 102, 101, 100],
            "high": [112, 116, 118, 118, 117, 105, 104, 103, 102, 101],
            "low": [99, 110, 114, 115, 112, 102, 101, 100, 99, 98],
            "close": [112, 116, 118, 117, 114, 104, 103, 102, 101, 100],
            "volume": [500, 550, 600, 620, 500, 180, 170, 160, 150, 140],
        },
        index=index,
    )
    events = pd.DataFrame(
        [
            {
                "announcement_id": "evt-1",
                "inst_id": "DOGE-USDT-SWAP",
                "listing_time": index[0],
            }
        ]
    )

    strategy = ListingFadeStrategy()
    signals = strategy.compute_signals(market_data, events)

    assert len(signals) == 1
    signal = signals.iloc[0]
    assert signal["signal"] == -1
    assert signal["event_id"] == "evt-1"
    assert signal["stop_price"] > signal["entry_price"]
    assert signal["target_price"] < signal["entry_price"]
