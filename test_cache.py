"""Test cache_raw with downloaded Binance data."""
from datetime import date
import pandas as pd
from src.backtest.loader import cache_raw

path = cache_raw('BTCUSDT', date(2026, 6, 20), date(2026, 6, 25))
print(f"Cached at: {path}")

df = pd.read_parquet(path)
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")
print(f"Index range: {df.index.min()} to {df.index.max()}")
print(f"Rows: {len(df)}")
print(f"OI non-null: {df['oi_value'].notna().sum()}")
print(f"OI sample:\n{df['oi_value'].dropna().head(3)}")
print(f"Close sample:\n{df['close'].head(3)}")
