import pandas as pd

from src.backtest.event_loader import build_event_windows, slice_event_window


def test_slice_event_window_bounds_are_inclusive():
    index = pd.date_range("2026-06-25 00:00:00", periods=10, freq="1min", tz="UTC")
    frame = pd.DataFrame({"close": range(10)}, index=index)

    window = slice_event_window(frame, index[4], lookback_minutes=2, lookahead_minutes=3)

    assert list(window.index) == list(index[2:8])


def test_build_event_windows_matches_inst_id():
    index = pd.date_range("2026-06-25 00:00:00", periods=20, freq="1min", tz="UTC")
    market_data = {
        "DOGE-USDT-SWAP": pd.DataFrame({"close": range(20)}, index=index),
    }
    events = pd.DataFrame(
        [
            {
                "inst_id": "DOGE-USDT-SWAP",
                "listing_time": index[10],
                "announcement_id": "1",
            }
        ]
    )

    windows = build_event_windows(market_data, events, lookahead_minutes=5)

    assert len(windows) == 1
    assert windows[0]["event"]["inst_id"] == "DOGE-USDT-SWAP"
    assert len(windows[0]["market_data"]) == 6
