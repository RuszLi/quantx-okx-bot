from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_strategy_report(strategy_name: str, metrics: dict[str, object], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {strategy_name} Report",
        "",
        f"DECISION: {metrics.get('decision', 'UNKNOWN')}",
        "",
        "## Metrics",
        "",
    ]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_paper_report(trades: pd.DataFrame, out_path: str | Path, slippage_bps: float) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    avg_pnl = float(trades["pnl_R"].mean()) if not trades.empty and "pnl_R" in trades else 0.0
    lines = [
        "# Paper Trading Report",
        "",
        f"- n_trades: {len(trades)}",
        f"- avg_pnl_R: {avg_pnl}",
        f"- slippage_bps: {slippage_bps}",
        "",
        "## Strategies",
        "",
    ]
    if not trades.empty and "strategy_name" in trades:
        for strategy_name, count in trades["strategy_name"].value_counts().items():
            lines.append(f"- {strategy_name}: {count}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
