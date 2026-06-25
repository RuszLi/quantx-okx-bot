"""Debug: raw taker buy/sell ratio at per-bar level."""
import sys, pandas as pd, numpy as np
from datetime import date
from src.backtest.loader import load_klines

symbol = sys.argv[1] if len(sys.argv) > 1 else "SOLUSDT"
start = date(2026, 5, 17)
end = date(2026, 5, 31)

k = load_klines(symbol, start, end)
print(f"Total bars: {len(k)}")
print(f"Columns: {list(k.columns)}")

tbb = k["taker_buy_quote_volume"].fillna(0)
qv = k["quote_volume"].fillna(0)
tbs = (qv - tbb).clip(lower=0)

# Per-bar flow imbalance
fi = np.where(qv > 0, (tbb - tbs) / qv, 0)
sr = np.abs(fi)

print(f"\ntaker_buy_quote_volume stats:")
print(f"  mean: {tbb.mean():.1f}, max: {tbb.max():.1f}, min: {tbb.min():.1f}")
print(f"quote_volume stats:")
print(f"  mean: {qv.mean():.1f}, max: {qv.max():.1f}")

print(f"\nPer-bar single_side_ratio stats (no rolling):")
print(f"  mean: {np.mean(sr):.4f}")
print(f"  max: {np.max(sr):.4f}")
print(f"  P99: {np.percentile(sr, 99):.4f}")
print(f"  P99.9: {np.percentile(sr, 99.9):.4f}")
print(f"  >0.80 count: {(sr > 0.80).sum()} / {len(sr)}")

# With 1-bar rolling (effectively no smoothing)
print(f"\nWith 1-bar rolling (same as no smoothing at 1-min):")
fi1 = pd.Series(fi).rolling(1, min_periods=1).mean()
sr1 = fi1.abs()
print(f"  >0.80 count: {(sr1 > 0.80).sum()}")

# Rolling 60 bar
print(f"\nWith 60-bar rolling (what code currently does):")
fi60 = pd.Series(fi).rolling(60, min_periods=10).mean()
sr60 = fi60.abs()
print(f"  max: {sr60.max():.4f}")
print(f"  >0.80 count: {(sr60 > 0.80).sum()}")
