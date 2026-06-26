"""Test which symbols are available and download missing data."""
from pathlib import Path
from datetime import date
from src.backtest.downloader import run as download_run
import asyncio

symbols = [
    "SOLUSDT", "DOGEUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT",
    "LINKUSDT", "POLUSDT", "ARBUSDT", "OPUSDT", "APTUSDT",
    "SUIUSDT", "INJUSDT", "NEARUSDT", "LDOUSDT", "WIFUSDT",
    "FETUSDT", "RENDERUSDT", "TIAUSDT", "SEIUSDT", "ATOMUSDT",
    "DOTUSDT", "FILUSDT", "BCHUSDT", "LTCUSDT"
]

start = date(2026, 6, 12)
end = date(2026, 6, 25)
kinds = ["klines_1m", "metrics"]

result = asyncio.run(download_run(symbols, start, end, kinds, 4))
print(f"OK: {result['counts'].get('ok', 0)}")
print(f"Cached: {result['counts'].get('cached', 0)}")
print(f"404: {result['counts'].get('404', 0)}")
print(f"Err: {result['counts'].get('err', 0)}")
print(f"Samples: {result['err_samples'][:5]}")
