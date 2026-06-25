from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.backtest.report_writer import write_paper_report
from src.reports.phase0 import write_phase0_combo_report, write_phase0_strategy_report
from src.reports.signoff import write_api_signoff_report, write_execution_feasibility_report


def generate_all_reports(
    reports_dir: str | Path,
    strategy_metrics: dict[str, dict[str, object]],
    combo_summary: pd.DataFrame,
    paper_trades: pd.DataFrame,
    api_checks: dict[str, dict[str, object]],
    execution_rows: list[dict[str, object]],
    slippage_bps: float,
) -> dict[str, Path]:
    out_dir = Path(reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs: dict[str, Path] = {}
    outputs["api_signoff"] = write_api_signoff_report(api_checks, out_dir / "v3_api_signoff.md")
    outputs["execution_feasibility"] = write_execution_feasibility_report(execution_rows, out_dir / "v3_execution_feasibility.md")
    outputs["phase0_combo"] = write_phase0_combo_report(combo_summary, out_dir / "v3_phase0_combo.md")
    outputs["paper"] = write_paper_report(paper_trades, out_dir / "v3_paper.md", slippage_bps=slippage_bps)

    for strategy_name, metrics in strategy_metrics.items():
        outputs[strategy_name] = write_phase0_strategy_report(strategy_name, metrics, out_dir / f"v3_{strategy_name}.md")

    return outputs


def _load_json(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--strategy-metrics-json", required=True)
    parser.add_argument("--combo-summary-csv", required=True)
    parser.add_argument("--paper-trades-csv", required=True)
    parser.add_argument("--api-checks-json", required=True)
    parser.add_argument("--execution-rows-json", required=True)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    args = parser.parse_args()

    strategy_metrics = _load_json(args.strategy_metrics_json)
    combo_summary = pd.read_csv(args.combo_summary_csv)
    paper_trades = pd.read_csv(args.paper_trades_csv)
    api_checks = _load_json(args.api_checks_json)
    execution_rows = _load_json(args.execution_rows_json)

    generate_all_reports(
        reports_dir=args.reports_dir,
        strategy_metrics=strategy_metrics,
        combo_summary=combo_summary,
        paper_trades=paper_trades,
        api_checks=api_checks,
        execution_rows=execution_rows,
        slippage_bps=args.slippage_bps,
    )


if __name__ == "__main__":
    main()
