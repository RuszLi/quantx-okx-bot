from __future__ import annotations

import json
from pathlib import Path

from src.reports.collect_inputs import collect_report_inputs
from src.reports.generate import generate_all_reports


def build_report_bundle(
    backtests_dir: str | Path,
    reports_dir: str | Path,
    api_checks_json: str | Path,
    execution_rows_json: str | Path,
    slippage_bps: float,
) -> dict[str, Path]:
    api_checks = json.loads(Path(api_checks_json).read_text(encoding="utf-8"))
    execution_rows = json.loads(Path(execution_rows_json).read_text(encoding="utf-8"))

    inputs = collect_report_inputs(
        backtests_dir=backtests_dir,
        api_checks=api_checks,
        execution_rows=execution_rows,
    )

    return generate_all_reports(
        reports_dir=reports_dir,
        strategy_metrics=inputs["strategy_metrics"],
        combo_summary=inputs["combo_summary"],
        paper_trades=inputs["paper_trades"],
        api_checks=inputs["api_checks"],
        execution_rows=inputs["execution_rows"],
        slippage_bps=slippage_bps,
    )
