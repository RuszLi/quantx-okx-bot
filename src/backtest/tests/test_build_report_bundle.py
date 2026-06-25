import json
from pathlib import Path

import pandas as pd

from src.reports.workflow import build_report_bundle


def test_build_report_bundle_creates_reports_from_backtest_dirs(tmp_path: Path):
    backtests_dir = tmp_path / "backtests"
    backtests_dir.mkdir()
    listing_dir = backtests_dir / "listing_fade"
    listing_dir.mkdir()

    pd.DataFrame([
        {"decision": "PASS", "win_rate": 0.60, "ev_R": 0.45, "profit_factor": 1.6, "max_consec_losses": 4, "n_trades": 50}
    ]).to_json(listing_dir / "summary.json", orient="records")
    pd.DataFrame([
        {"strategy_name": "listing_fade", "pnl_R": 0.5, "mode": "paper"}
    ]).to_csv(listing_dir / "trades.csv", index=False)

    api_checks_path = tmp_path / "api_checks.json"
    execution_rows_path = tmp_path / "execution_rows.json"
    api_checks_path.write_text(json.dumps({"instruments": {"status": "PASS", "evidence": "ok"}}), encoding="utf-8")
    execution_rows_path.write_text(json.dumps([{"instId": "BTC-USDT-SWAP", "minSz": 0.01, "lotSz": 0.01, "tickSz": 0.1, "ctVal": 0.01, "can_open_position": True, "can_place_hard_stop": True, "can_post_only_fill": True}]), encoding="utf-8")

    reports_dir = tmp_path / "reports"
    outputs = build_report_bundle(
        backtests_dir=backtests_dir,
        reports_dir=reports_dir,
        api_checks_json=api_checks_path,
        execution_rows_json=execution_rows_path,
        slippage_bps=3.0,
    )

    assert (reports_dir / "v3_api_signoff.md").exists()
    assert (reports_dir / "v3_execution_feasibility.md").exists()
    assert (reports_dir / "v3_phase0_combo.md").exists()
    assert (reports_dir / "v3_paper.md").exists()
    assert (reports_dir / "v3_listing_fade.md").exists()
    assert outputs["paper"].name == "v3_paper.md"
