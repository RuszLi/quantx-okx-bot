"""Data layer — unified interface for fetching and caching market data.

Every function returns a ``pd.DataFrame`` with UTC timestamp index and a
``point_in_time`` boolean column indicating whether each field is live-visible
at the row timestamp.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

if TYPE_CHECKING:
    import sys

    if sys.version_info >= (3, 11):
        from typing import Self
    else:
        from typing_extensions import Self


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"

__all__ = [
    "get_klines",
    "get_funding",
    "get_open_interest",
    "get_order_book_snapshot",
    "get_liquidations",
]


def _utc(ts: Any) -> pd.Timestamp:
    """Coerce *ts* to timezone-aware UTC.

    Raises ``ValueError`` if already aware and not UTC.
    """
    t = pd.Timestamp(ts)
    if t.tz is not None and str(t.tz) != "UTC":
        raise ValueError(f"Timestamp {ts} is not UTC")
    return t.tz_localize("UTC") if t.tz is None else t


def _normalize_timestamp_series(series: pd.Series) -> pd.DatetimeIndex:
    if is_datetime64_any_dtype(series):
        return pd.DatetimeIndex(pd.to_datetime(series, utc=True, errors="coerce"))
    non_null = series.dropna()
    if not non_null.empty and isinstance(non_null.iloc[0], pd.Timestamp):
        return pd.DatetimeIndex(pd.to_datetime(series, utc=True, errors="coerce"))
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().any():
        return pd.DatetimeIndex(pd.to_datetime(numeric, unit="ms", utc=True, errors="coerce"))
    return pd.DatetimeIndex(pd.to_datetime(series, utc=True, errors="coerce"))


# ---------------------------------------------------------------------------
# Internal helpers — delegation to existing backtest/loader & src/data/*
# ---------------------------------------------------------------------------

def _loader_klines(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Thin wrapper around ``loader.load_klines``."""
    from src.backtest.loader import load_klines

    return load_klines(symbol, start, end)


def _loader_metrics(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Thin wrapper around ``loader.load_metrics``."""
    from src.backtest.loader import load_metrics

    return load_metrics(symbol, start, end)


def _loader_liquidations(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Thin wrapper around ``loader.load_liquidations``."""
    from src.backtest.loader import load_liquidations

    return load_liquidations(symbol, start, end)


def _loader_cache_raw(symbol: str, start: date, end: date) -> Path:
    """Thin wrapper around ``loader.cache_raw``."""
    from src.backtest.loader import cache_raw

    return cache_raw(symbol, start, end)


def _okx_funding(inst_id: str, limit: int = 200) -> pd.DataFrame:
    """Thin wrapper around ``okx_funding.fetch_funding_history``."""
    from src.data.okx_funding import fetch_funding_history

    return fetch_funding_history(inst_id, limit=limit)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_klines(
    symbol: str,
    freq: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Fetch OHLCV klines for a symbol.

    Priority: local parquet -> Binance daily zip -> (fallback) OKX REST.

    Parameters
    ----------
    symbol : str
        Binance symbol (e.g. ``"BTCUSDT"``).
    freq : str
        Target bar frequency (e.g. ``"1m"``, ``"1h"``). When the requested
        frequency is coarser than ``"1m"`` the data is resampled **after**
        loading the 1-minute base.
    start : pd.Timestamp
        Inclusive UTC start.
    end : pd.Timestamp
        Exclusive UTC end.

    Returns
    -------
    pd.DataFrame
        Columns: ``open, high, low, close, volume, quote_volume,
        taker_buy_quote, taker_sell_quote, point_in_time``.
        Index is UTC-aligned at the requested frequency.
    """
    s, e = (_utc(t).date() for t in (start, end))
    if s >= e:
        return pd.DataFrame()

    try:
        path = _loader_cache_raw(symbol, s, e)
        raw = pd.read_parquet(path)
    except (ValueError, FileNotFoundError):
        # Fallback: OKX parquet cache or live download
        processed_dir = DATA_ROOT / "processed"
        okx_path = processed_dir / f"{symbol}_raw.parquet"
        if okx_path.exists():
            raw = pd.read_parquet(okx_path)
        else:
            # Cannot fetch live data here — this is a read-only data layer.
            raise FileNotFoundError(
                f"No cached data for {symbol} in [{s}, {e}]. "
                "Run download scripts first."
            )

    # Resample to target frequency if needed
    if freq != "1m":
        ohlc_dict = {"open": "first", "high": "max", "low": "min", "close": "last"}
        vol_dict = {"volume": "sum", "quote_volume": "sum",
                    "taker_buy_quote": "sum", "taker_sell_quote": "sum"}
        raw = raw.resample(freq).agg({**ohlc_dict, **vol_dict}).dropna(subset=["open"])

    # point_in_time: all OHLCV fields are live-visible at bar close
    raw["point_in_time"] = True

    return raw


def get_funding(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Fetch funding-rate history for a symbol from OKX API.

    The returned DataFrame is indexed by UTC timestamp (1-minute alignment).
    The ``point_in_time`` column is True only for rows whose funding rate
    was known before the next settlement.

    Parameters
    ----------
    symbol : str
        Trading pair (e.g. ``"BTC-USDT-SWAP"``).
    start : pd.Timestamp
        Inclusive UTC start.
    end : pd.Timestamp
        Exclusive UTC end.

    Returns
    -------
    pd.DataFrame
        Columns: ``funding_rate, next_funding_time, point_in_time``.
        Empty DataFrame if OKX API unavailable.
    """
    start_ts = _utc(start).floor("1min")
    end_ts = _utc(end).floor("1min")
    if start_ts >= end_ts:
        return pd.DataFrame()
    s, e = start_ts.date(), end_ts.date()
    master = pd.date_range(
        start_ts - pd.Timedelta(days=1),
        end_ts + pd.Timedelta(days=1),
        freq="1min",
        tz="UTC",
        name="ts",
    )

    try:
        funding = _okx_funding(symbol, limit=200)
        if funding.empty or "funding_rate" not in funding.columns:
            return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

    funding = funding.rename(columns={"funding_time": "ts"}).copy()
    funding["ts"] = _normalize_timestamp_series(funding["ts"])
    funding = funding.dropna(subset=["ts"]).set_index("ts")
    funding = funding[["funding_rate"]].sort_index()
    if not funding.index.is_unique:
        funding = funding[~funding.index.duplicated(keep="last")]

    # Reindex to master 1-minute, forward-fill limit=500 (~8h)
    result = pd.DataFrame(index=master)
    result["funding_rate"] = (
        funding["funding_rate"]
        .reindex(master, method="ffill", limit=500)
    )

    # Compute next_funding_time (the nearest funding_time AFTER each bar)
    settlement_times = sorted(funding.index)
    result["next_funding_time"] = pd.NaT
    if settlement_times:
        nft = pd.Series(index=master, dtype="datetime64[ns, UTC]")
        idx = 0
        for ts in master:
            while idx < len(settlement_times) and settlement_times[idx] <= ts:
                idx += 1
            if idx < len(settlement_times):
                nft[ts] = settlement_times[idx]
        result["next_funding_time"] = nft

    # point_in_time: True when funding_rate is known before settlement
    result["point_in_time"] = result.apply(
        lambda r: r["next_funding_time"] > r.name
        if pd.notna(r["next_funding_time"])
        else False,
        axis=1,
    )

    # Slice to requested window and drop leading NaN rows that fell outside the
    # real data range
    return result.loc[start_ts : end_ts - pd.Timedelta(minutes=1)]


def get_open_interest(
    symbol: str,
    freq: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Fetch open-interest history for a symbol.

    OI data is sampled at 5-minute granularity and forward-filled to 1-minute.

    Parameters
    ----------
    symbol : str
        Binance symbol (e.g. ``"BTCUSDT"``).
    freq : str
        Sampling frequency (currently only ``"5m"`` supported).
    start : pd.Timestamp
        Inclusive UTC start.
    end : pd.Timestamp
        Exclusive UTC end.

    Returns
    -------
    pd.DataFrame
        Columns: ``oi_value, oi_value_diff_5m, point_in_time``.
    """
    s, e = (_utc(t).date() for t in (start, end))
    try:
        metrics = _loader_metrics(symbol, s, e)
    except ValueError:
        return pd.DataFrame()
    if metrics.empty or "sum_open_interest_value" not in metrics.columns:
        return pd.DataFrame()

    oi = metrics[["sum_open_interest_value"]].rename(
        columns={"sum_open_interest_value": "oi_value"}
    )
    master = pd.date_range(
        _utc(s), _utc(e) - pd.Timedelta(minutes=1), freq="1min", tz="UTC", name="ts",
    )
    result = pd.DataFrame(index=master)
    result["oi_value"] = oi["oi_value"].reindex(master, method="ffill", limit=5)
    result["oi_value_diff_5m"] = result["oi_value"].diff(5)
    result["point_in_time"] = True  # OI snapshots are point-in-time at snapshot timestamp

    return result


def get_order_book_snapshot(
    symbol: str,
    ts: pd.Timestamp,
) -> pd.DataFrame | None:
    """Stub — order-book snapshots not yet indexed.

    Parameters
    ----------
    symbol : str
        Trading pair.
    ts : pd.Timestamp
        UTC timestamp of the snapshot.

    Returns
    -------
    pd.DataFrame | None
        ``None`` until order-book data ingestion is added in a future phase.
    """
    _ = symbol, ts
    return None


def get_liquidations(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Fetch liquidation events for a symbol, aggregated to 1-minute buckets.

    Parameters
    ----------
    symbol : str
        Binance symbol (e.g. ``"BTCUSDT"``).
    start : pd.Timestamp
        Inclusive UTC start.
    end : pd.Timestamp
        Exclusive UTC end.

    Returns
    -------
    pd.DataFrame
        Columns: ``liq_buy_usd, liq_sell_usd, liq_total_usd, point_in_time``.
    """
    s, e = (_utc(t).date() for t in (start, end))
    try:
        liq = _loader_liquidations(symbol, s, e)
    except Exception:
        return pd.DataFrame()
    if liq.empty or "usd" not in liq.columns or "side" not in liq.columns:
        return pd.DataFrame()

    liq = liq.dropna(subset=["ts", "side", "usd"])
    if liq.empty:
        return pd.DataFrame()

    master = pd.date_range(
        _utc(s), _utc(e) - pd.Timedelta(minutes=1), freq="1min", tz="UTC", name="ts",
    )
    liq_min = (
        liq.set_index("ts")
        .groupby([pd.Grouper(freq="1min"), "side"])["usd"]
        .sum()
        .unstack(fill_value=0)
    )
    buy_key = next((c for c in liq_min.columns if c.upper() == "BUY"), None)
    sell_key = next((c for c in liq_min.columns if c.upper() == "SELL"), None)

    result = pd.DataFrame(index=master, dtype="float64")
    result["liq_buy_usd"] = (
        (liq_min[buy_key].reindex(master).fillna(0.0).astype("float64"))
        if buy_key is not None
        else 0.0
    )
    result["liq_sell_usd"] = (
        (liq_min[sell_key].reindex(master).fillna(0.0).astype("float64"))
        if sell_key is not None
        else 0.0
    )
    result["liq_total_usd"] = result["liq_buy_usd"] + result["liq_sell_usd"]
    result["point_in_time"] = True  # liquidations are published in near-real-time

    return result
