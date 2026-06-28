"""Alpha (FR-Switch) + Gamma (SC) backtest runner.

Runs both strategies on 3 months of BTC-USDT history and validates
metrics against the PASS gate (win_rate≥0.55, ev_R≥0.3, profit_factor≥1.4).

Usage:
    python scripts/run_alpha_gamma_backtest.py

Output:
    reports/alpha_gamma/<strategy_name>_trades.csv
    reports/alpha_gamma/summary.json
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.run import run_named_strategy
from src.backtest.metrics import compute_metrics, save_summary


def main() -> None:
    start = date(2026, 3, 1)
    end = date(2026, 6, 1)
    out_dir = ROOT / "reports" / "alpha_gamma"
    out_dir.mkdir(parents=True, exist_ok=True)

    strategies = ["alpha_funding_switch", "gamma_settlement_compression"]
    results = {}

    for name in strategies:
        print(f"\n=== Running {name} ===")
        trades, summary = run_named_strategy(
            strategy_name=name,
            start=start,
            end=end,
            universe_path=None,
            out_dir=out_dir,
        )
        print(f"Signals: {summary['signals']}, Symbols: {summary['symbols']}")

        if trades.empty:
            print("No trades produced.")
            results[name] = {"status": "NO_TRADES", "summary": summary}
            continue

        metrics = compute_metrics(trades, n_symbols=summary['symbols'], n_days=(end - start).days)
        gate = metrics.get("gate", "UNKNOWN")
        print(f"Gate: {gate}")
        print(f"  win_rate={metrics.get('win_rate', 0):.3f}")
        print(f"  ev_R={metrics.get('ev_R', 0):.3f}")
        print(f"  profit_factor={metrics.get('profit_factor', 0):.3f}")
        print(f"  tps={metrics.get('tps', 0)}")
        print(f"  max_consec_losses={metrics.get('max_consec_losses', 0)}")
        print(f"  total_trades={metrics.get('total_trades', 0)}")

        results[name] = {
            "status": gate,
            "summary": summary,
            "metrics": metrics,
        }

    # Save combined summary
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print("\n=== Combined Results ===")
    for name, r in results.items():
        print(f"{name}: {r['status']}")


if __name__ == "__main__":
    main()
