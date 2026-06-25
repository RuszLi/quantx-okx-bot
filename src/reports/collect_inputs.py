from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _load_summary(summary_path: Path) -> dict[str, object]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload[0] if payload else {}
    return payload


def collect_report_inputs(
    backtests_dir: str | Path,
    api_checks: dict[str, dict[str, object]],
    execution_rows: list[dict[str, object]],
) -> dict[str, object]:
    base = Path(backtests_dir)
    strategy_metrics: dict[str, dict[str, object]] = {}
    combo_rows: list[dict[str, object]] = []
    paper_trades_frames: list[pd.DataFrame] = []

    for strategy_dir in sorted(path for path in base.iterdir() if path.is_dir()):
        summary_path = strategy_dir / "summary.json"
        trades_path = strategy_dir / "trades.csv"
        if not summary_path.exists():
            continue

        metrics = _load_summary(summary_path)
        strategy_name = strategy_dir.name
        strategy_metrics[strategy_name] = metrics

        combo_row = {"strategy_name": strategy_name}
        combo_row.update(metrics)
        combo_rows.append(combo_row)

        if trades_path.exists():
            trades = pd.read_csv(trades_path)
            if "strategy_name" not in trades.columns:
                trades["strategy_name"] = strategy_name
            paper_trades_frames.append(trades)

    combo_summary = pd.DataFrame(combo_rows)
    paper_trades = pd.concat(paper_trades_frames, ignore_index=True) if paper_trades_frames else pd.DataFrame()

    normalized_checks: dict[str, dict[str, object]] = {}
    for key, item in api_checks.items():
        if isinstance(item, dict) and "status" in item:
            normalized_checks[key] = item
        elif isinstance(item, dict) and "ok" in item:
            ok = bool(item.get("ok", False))
            evidence_parts = []
            if "count" in item:
                evidence_parts.append(f"count={item['count']}")
            if "gap_pct" in item:
                evidence_parts.append(f"gap_pct={item['gap_pct']}")
            normalized_checks[key] = {
                "status": "PASS" if ok else "ABORT",
                "evidence": ", ".join(evidence_parts) or str(item),
            }
        else:
            normalized_checks[key] = {"status": "UNKNOWN", "evidence": str(item)}

    return {
        "strategy_metrics": strategy_metrics,
        "combo_summary": combo_summary,
        "paper_trades": paper_trades,
        "api_checks": normalized_checks,
        "execution_rows": execution_rows,
    }
