"""Build data inventory JSON for Phase 0 backtest.
Reads data/raw/ directory structure and checks completeness.
Usage: python scripts/build_inventory.py --symbols SOLUSDT DOGEUSDT ... --start 2026-05-15 --end 2026-06-24
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"
KINDS = ["klines_1m", "metrics", "liquidationSnapshot"]


def symbol_has_data(symbol: str, d: date, kind: str) -> bool:
    p = DATA_ROOT / kind / symbol / f"{symbol}-{kind}-{d.isoformat()}.zip"
    return p.exists() and p.stat().st_size > 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    args = p.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    inventory = {"start": str(start), "end": str(end), "symbols": {}}

    for sym in args.symbols:
        sym_data = {"klines_missing": [], "metrics_missing": [], "liq_missing": []}
        d = start
        while d <= end:
            for kind in KINDS:
                if not symbol_has_data(sym, d, kind):
                    if kind == "klines_1m":
                        sym_data["klines_missing"].append(d.isoformat())
                    elif kind == "metrics":
                        sym_data["metrics_missing"].append(d.isoformat())
                    else:
                        sym_data["liq_missing"].append(d.isoformat())
            d += timedelta(days=1)

        # exclude if klines or metrics missing > 5 days
        skip = len(sym_data["klines_missing"]) > 5 or len(sym_data["metrics_missing"]) > 5
        total_missing_liq = len(sym_data["liq_missing"])
        total_days = (end - start).days + 1
        sym_data["excluded"] = skip
        sym_data["n_klines_ok"] = total_days - len(sym_data["klines_missing"])
        sym_data["n_metrics_ok"] = total_days - len(sym_data["metrics_missing"])
        sym_data["n_liq_ok"] = total_days - total_missing_liq
        sym_data["liquidation_seems_404"] = (total_missing_liq == total_days)
        inventory["symbols"][sym] = sym_data

    out = DATA_ROOT / "_inventory.json"
    out.write_text(json.dumps(inventory, indent=2, ensure_ascii=False))
    print(f"Inventory written to {out}")

    excluded = [s for s, d in inventory["symbols"].items() if d["excluded"]]
    included = [s for s, d in inventory["symbols"].items() if not d["excluded"]]
    print(f"Included: {len(included)} symbols, Excluded: {len(excluded)} symbols")
    if excluded:
        print(f"Excluded: {excluded}")
    all_liq_404 = all(d["liquidation_seems_404"] for d in inventory["symbols"].values())
    print(f"All liquidationSnapshot 404? {all_liq_404}  -> will use OI proxy path")


if __name__ == "__main__":
    main()
