from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_phase0_strategy_report(strategy_name: str, metrics: dict[str, object], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {strategy_name} Phase 0.5 Report",
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


def write_phase0_combo_report(summary: pd.DataFrame, out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pass_rows = summary.loc[summary["decision"] == "PASS"] if not summary.empty else pd.DataFrame()
    lines = [
        "# V3 Phase 0 Combo Report",
        "",
        "## Live Candidates",
        "",
    ]
    if pass_rows.empty:
        lines.append("- none")
    else:
        for _, row in pass_rows.iterrows():
            lines.append(f"- {row['strategy_name']}: ev_R={row.get('ev_R', '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
