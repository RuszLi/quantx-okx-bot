from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_listing_events(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    for column in ["published_at", "listing_time"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    return frame


def slice_event_window(
    market_data: pd.DataFrame,
    anchor_ts: pd.Timestamp,
    lookback_minutes: int = 0,
    lookahead_minutes: int = 60,
) -> pd.DataFrame:
    start_ts = anchor_ts - pd.Timedelta(minutes=lookback_minutes)
    end_ts = anchor_ts + pd.Timedelta(minutes=lookahead_minutes)
    return market_data.loc[(market_data.index >= start_ts) & (market_data.index <= end_ts)].copy()


def build_event_windows(
    market_data_by_symbol: dict[str, pd.DataFrame],
    events: pd.DataFrame,
    lookback_minutes: int = 0,
    lookahead_minutes: int = 60,
) -> list[dict[str, object]]:
    windows: list[dict[str, object]] = []
    for _, event in events.iterrows():
        inst_id = str(event.get("inst_id") or "")
        market_data = market_data_by_symbol.get(inst_id)
        listing_time = event.get("listing_time")
        if market_data is None or pd.isna(listing_time):
            continue
        window = slice_event_window(
            market_data=market_data,
            anchor_ts=pd.Timestamp(listing_time),
            lookback_minutes=lookback_minutes,
            lookahead_minutes=lookahead_minutes,
        )
        if window.empty:
            continue
        windows.append({"event": event.to_dict(), "market_data": window})
    return windows
