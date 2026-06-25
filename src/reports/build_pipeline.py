from __future__ import annotations

from datetime import date
from pathlib import Path

from src.backtest.batch_runner import run_batch_strategies
from src.reports.collect_inputs import collect_report_inputs
from src.reports.generate import generate_all_reports
from src.reports.okx_public_probe import run_public_probe
from src.reports.probe_okx import build_execution_rows


def run_v3_pipeline(
    strategy_names: list[str],
    start: str,
    end: str,
    universe_path: str | None,
    backtests_dir: Path,
    probe_payload_json: Path,
    instrument_payload_json: Path,
    probe_out_dir: Path,
    reports_dir: Path,
    slippage_bps: float,
    skip_batch_run: bool = False,
) -> dict[str, object]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    if not skip_batch_run:
        run_batch_strategies(strategy_names, start_date, end_date, universe_path, backtests_dir)

    probe_out_dir.mkdir(parents=True, exist_ok=True)
    import json

    if probe_payload_json.exists():
        probe_payload = json.loads(probe_payload_json.read_text(encoding="utf-8"))
    else:
        probe_payload = run_public_probe(strategy_names[0] if strategy_names else "BTC-USDT-SWAP")
        probe_payload_json.write_text(json.dumps(probe_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    instrument_payload = json.loads(instrument_payload_json.read_text(encoding="utf-8"))
    api_checks = probe_payload
    execution_rows = build_execution_rows(instrument_payload)

    inputs = collect_report_inputs(backtests_dir=backtests_dir, api_checks=api_checks, execution_rows=execution_rows)
    outputs = generate_all_reports(
        reports_dir=reports_dir,
        strategy_metrics=inputs["strategy_metrics"],
        combo_summary=inputs["combo_summary"],
        paper_trades=inputs["paper_trades"],
        api_checks=inputs["api_checks"],
        execution_rows=inputs["execution_rows"],
        slippage_bps=slippage_bps,
    )
    return {"inputs": inputs, "outputs": outputs}
