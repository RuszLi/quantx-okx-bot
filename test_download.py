"""Test OKX kline download."""
from datetime import date
from src.data.okx_klines import fetch_candles_range, download_and_cache

df = fetch_candles_range("SOL-USDT-SWAP", date(2026, 6, 12), date(2026, 6, 25), bar="1m", delay=0.05)
print(f"Rows: {len(df)}")
print(f"Range: {df['ts'].min()} to {df['ts'].max()}")
days = (df["ts"].max() - df["ts"].min()).total_seconds() / 86400
print(f"Days: {days:.1f}")

# Now test full pipeline
df2 = download_and_cache("SOL-USDT-SWAP", date(2026, 6, 12), date(2026, 6, 25))
print(f"\nCached: {len(df2)} rows")
print(f"Cached range: {df2.index.min()} to {df2.index.max()}")
