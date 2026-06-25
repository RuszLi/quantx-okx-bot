"""
loader.py — Phase 0 backtest data loader.
Reads raw zips from Binance public data, unifies to 1-min UTC index,
and outputs a single parquet per symbol with columns:
  ts, open, high, low, close, volume, quote_volume,
  taker_buy_quote, taker_sell_quote, oi_value, oi_value_diff_5m,
  liq_buy_usd, liq_sell_usd
"""
from __future__ import annotations

import zipfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def _read_csv_with_header_detect(zf: zipfile.ZipFile, name: str) -> pd.DataFrame:
    """Read a CSV from inside a zip, auto-detecting if first row is a header."""
    content = zf.read(name).decode("utf-8", errors="replace").strip()
    if not content:
        return pd.DataFrame()
    # try parsing first row's first field as float; if fails, assume header row
    first_line = content.split("\n")[0]
    first_field = first_line.split(",")[0]
    header = None
    try:
        float(first_field)
    except ValueError:
        header = "infer"
    return pd.read_csv(StringIO(content), header=header)


def _day_range(start: date, end: date):
    """Yield each date in [start, end] inclusive."""
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def load_klines(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Load all klines for a symbol, merge into a single 1-min DataFrame."""
    frames = []
    col_names = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "count", "taker_buy_volume",
        "taker_buy_quote_volume", "ignore",
    ]
    for d in _day_range(start, end):
        zp = DATA_ROOT / "raw" / "klines_1m" / symbol / f"{symbol}-klines_1m-{d.isoformat()}.zip"
        if not zp.exists() or zp.stat().st_size == 0:
            continue
        with zipfile.ZipFile(zp) as zf:
            names = [n for n in zf.namelist() if not n.startswith("__MACOSX/") and n.endswith(".csv")]
            if not names:
                continue
            for name in names:
                df = _read_csv_with_header_detect(zf, name)
                if df.empty:
                    continue
                df.columns = col_names[: len(df.columns)]
                frames.append(df)

    if not frames:
        raise ValueError(f"No klines data found for {symbol} in [{start}, {end}]")

    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.drop_duplicates(subset="ts").set_index("ts").sort_index()
    df = df[["open", "high", "low", "close", "volume", "quote_volume",
             "taker_buy_volume", "taker_buy_quote_volume"]]

    # Downcast float for memory
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df


def load_metrics(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Load all metrics CSVs, merge into a single 5-min DataFrame."""
    frames = []
    for d in _day_range(start, end):
        zp = DATA_ROOT / "raw" / "metrics" / symbol / f"{symbol}-metrics-{d.isoformat()}.zip"
        if not zp.exists() or zp.stat().st_size == 0:
            continue
        with zipfile.ZipFile(zp) as zf:
            names = [n for n in zf.namelist() if not n.startswith("__MACOSX/") and n.endswith(".csv")]
            if not names:
                continue
            for name in names:
                df = _read_csv_with_header_detect(zf, name)
                if df.empty:
                    continue
                frames.append(df)

    if not frames:
        raise ValueError(f"No metrics data found for {symbol} in [{start}, {end}]")

    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["create_time"], utc=True)
    df = df.drop_duplicates(subset="ts").set_index("ts").sort_index()

    # Cast numeric
    for c in ["sum_open_interest_value", "sum_open_interest"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    return df


def load_liquidations(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Load liquidation snapshots. May return empty if data entirely 404."""
    frames = []
    for d in _day_range(start, end):
        zp = DATA_ROOT / "raw" / "liquidationSnapshot" / symbol / f"{symbol}-liquidationSnapshot-{d.isoformat()}.zip"
        if not zp.exists() or zp.stat().st_size == 0:
            continue
        with zipfile.ZipFile(zp) as zf:
            names = [n for n in zf.namelist() if not n.startswith("__MACOSX/") and n.endswith(".csv")]
            if not names:
                continue
            for name in names:
                df = _read_csv_with_header_detect(zf, name)
                if df.empty:
                    continue
                frames.append(df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    if "time" in df.columns:
        df["ts"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    elif "create_time" in df.columns:
        df["ts"] = pd.to_datetime(df["create_time"], utc=True)
    else:
        return pd.DataFrame()

    # Compute USD = quantity * price
    qty_col = next((c for c in ["order_last_filled_quantity", "original_quantity"] if c in df.columns), None)
    px_col = next((c for c in ["average_price", "price"] if c in df.columns), None)
    if qty_col and px_col:
        for c in [qty_col, px_col]:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        df["usd"] = df[qty_col] * df[px_col]
    else:
        df["usd"] = 0.0

    return df


def build_raw(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Merge klines + metrics + liquidation into a single 1-min-indexed DataFrame."""
    # Load klines
    k = load_klines(symbol, start, end)
    if k.empty:
        raise ValueError(f"Empty klines for {symbol}")

    # Master 1-min index
    master = pd.date_range(k.index.min(), k.index.max(), freq="1min", tz="UTC", name="ts")
    raw = k.reindex(master)

    # ffill missing klines (up to 2 bars)
    raw = raw.ffill(limit=2)
    if raw.isnull().any().any():
        raise ValueError(f"Klines for {symbol} have gaps > 2 bars")

    # Derived columns
    raw["taker_buy_quote"] = raw["taker_buy_quote_volume"].fillna(0.0)
    raw["taker_sell_quote"] = raw["quote_volume"].fillna(0.0) - raw["taker_buy_quote"]
    raw["taker_sell_quote"] = raw["taker_sell_quote"].clip(lower=0)

    # Metrics
    try:
        m = load_metrics(symbol, start, end)
    except ValueError:
        m = pd.DataFrame()
    if not m.empty and "sum_open_interest_value" in m.columns:
        oi_5m = m[["sum_open_interest_value"]].rename(columns={"sum_open_interest_value": "oi_value"})
        # Reindex to master 1min, forward fill (limit 5 for 5min -> 1min)
        oi_1m = oi_5m.reindex(master, method="ffill", limit=5)
        raw["oi_value"] = oi_1m["oi_value"].astype("float64")
        raw["oi_value_diff_5m"] = raw["oi_value"].diff(5)
    else:
        raw["oi_value"] = np.nan
        raw["oi_value_diff_5m"] = np.nan

    # Liquidations
    liq = load_liquidations(symbol, start, end)
    if not liq.empty and "usd" in liq.columns and "side" in liq.columns:
        liq["side_bin"] = 1  # BUY
        liq_min = liq.set_index("ts").groupby([pd.Grouper(freq="1min"), "side"])["usd"].sum().unstack(fill_value=0)
        buy_key = next((c for c in liq_min.columns if c.upper() == "BUY"), None)
        sell_key = next((c for c in liq_min.columns if c.upper() == "SELL"), None)
        liq_1m = pd.DataFrame(index=master, data={"liq_buy_usd": np.nan, "liq_sell_usd": np.nan})
        if buy_key is not None:
            liq_1m["liq_buy_usd"] = liq_min[buy_key].reindex(master).fillna(0.0).astype("float64")
        if sell_key is not None:
            liq_1m["liq_sell_usd"] = liq_min[sell_key].reindex(master).fillna(0.0).astype("float64")
        raw["liq_buy_usd"] = liq_1m["liq_buy_usd"]
        raw["liq_sell_usd"] = liq_1m["liq_sell_usd"]
    else:
        raw["liq_buy_usd"] = np.nan
        raw["liq_sell_usd"] = np.nan

    return raw


def cache_raw(symbol: str, start: date, end: date, force: bool = False) -> Path:
    """Build raw data and cache to parquet. Returns path to cached file."""
    out_dir = DATA_ROOT / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{symbol}_raw.parquet"

    if out_path.exists() and not force:
        return out_path

    raw = build_raw(symbol, start, end)
    raw.to_parquet(out_path, index=True)
    return out_path
