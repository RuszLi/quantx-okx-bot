"""Test V3 backtest pipeline with real Binance data + proxy funding."""
from datetime import date
from pathlib import Path

from src.backtest.run import run_named_strategy

out_dir = Path("backtests/test_funding")
out_dir.mkdir(parents=True, exist_ok=True)

trades, summary = run_named_strategy(
    strategy_name="funding_extreme",
    start=date(2026, 6, 20),
    end=date(2026, 6, 25),
    universe_path=None,
    out_dir=out_dir,
)
print(f"Trades: {len(trades)}")
print(f"Summary: {summary}")
if not trades.empty:
    print(f"Columns: {list(trades.columns)}")
    for c in trades.columns:
        print(f"  {c}: {trades[c].dtype}, sample={trades[c].head(3).tolist()}")
