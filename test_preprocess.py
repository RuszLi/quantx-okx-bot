"""Pre-process all symbols through cache_raw to build parquet files."""
from datetime import date
from src.backtest.loader import cache_raw

symbols = [
    "BTCUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "LINKUSDT", "POLUSDT", "ARBUSDT", "OPUSDT",
    "APTUSDT", "SUIUSDT", "INJUSDT", "NEARUSDT", "LDOUSDT",
    "WIFUSDT", "FETUSDT", "RENDERUSDT", "TIAUSDT", "SEIUSDT",
    "ATOMUSDT", "DOTUSDT", "FILUSDT", "BCHUSDT", "LTCUSDT"
]
start = date(2026, 6, 12)
end = date(2026, 6, 25)

for i, sym in enumerate(symbols):
    try:
        path = cache_raw(sym, start, end)
        print(f"[{i+1}/{len(symbols)}] {sym}: OK -> {path.name}")
    except Exception as e:
        print(f"[{i+1}/{len(symbols)}] {sym}: FAIL - {e}")
