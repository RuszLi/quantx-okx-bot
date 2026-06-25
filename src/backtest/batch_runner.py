from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.backtest.metrics import compute_metrics
from src.backtest.run import run_named_strategy


def run_batch_strategies(
    strategy_names: list[str],
    start: date,
    end: date,
    universe_path: str | None,
    backtests_dir: str | Path,
) -> dict[str, Path]:
    out_root = Path(backtests_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    n_days = (end - start).days + 1

    for strategy_name in strategy_names:
        strategy_dir = out_root / strategy_name
        strategy_dir.mkdir(parents=True, exist_ok=True)
        trades, summary = run_named_strategy(strategy_name, start, end, universe_path, strategy_dir)

        trades_path = strategy_dir / "trades.csv"
        summary_path = strategy_dir / "summary.json"
        trades.to_csv(trades_path, index=False)

        if trades.empty:
            metrics = compute_metrics(pd.DataFrame(columns=["pnl_R", "exit_reason", "equity_after"]), 1, n_days)
        else:
            metrics = compute_metrics(trades, max(int(summary.get("symbols", 1)), 1), n_days)
        metrics["strategy_name"] = strategy_name
        summary_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
        outputs[strategy_name] = strategy_dir

    return outputs
