import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_generate_reports_cli_writes_outputs(tmp_path: Path):
    strategy_metrics = {"listing_fade": {"decision": "PASS", "ev_R": 0.45}}
    combo_summary = pd.DataFrame([{"strategy_name": "listing_fade", "decision": "PASS", "ev_R": 0.45}])
    paper_trades = pd.DataFrame([{"strategy_name": "listing_fade", "pnl_R": 0.5, "mode": "paper"}])
    api_checks = {"instruments": {"status": "PASS", "evidence": "ok"}}
    execution_rows = [{"instId": "BTC-USDT-SWAP", "minSz": 0.01, "lotSz": 0.01, "tickSz": 0.1, "ctVal": 0.01, "can_open_position": True, "can_place_hard_stop": True, "can_post_only_fill": True}]

    strategy_metrics_path = tmp_path / "strategy_metrics.json"
    combo_summary_path = tmp_path / "combo_summary.csv"
    paper_trades_path = tmp_path / "paper_trades.csv"
    api_checks_path = tmp_path / "api_checks.json"
    execution_rows_path = tmp_path / "execution_rows.json"
    reports_dir = tmp_path / "reports"

    strategy_metrics_path.write_text(json.dumps(strategy_metrics), encoding="utf-8")
    combo_summary.to_csv(combo_summary_path, index=False)
    paper_trades.to_csv(paper_trades_path, index=False)
    api_checks_path.write_text(json.dumps(api_checks), encoding="utf-8")
    execution_rows_path.write_text(json.dumps(execution_rows), encoding="utf-8")

    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = str(repo_root)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.reports.generate",
            "--reports-dir",
            str(reports_dir),
            "--strategy-metrics-json",
            str(strategy_metrics_path),
            "--combo-summary-csv",
            str(combo_summary_path),
            "--paper-trades-csv",
            str(paper_trades_path),
            "--api-checks-json",
            str(api_checks_path),
            "--execution-rows-json",
            str(execution_rows_path),
        ],
        check=True,
        cwd=tmp_path,
        env=env,
    )

    assert (reports_dir / "v3_api_signoff.md").exists()
    assert (reports_dir / "v3_execution_feasibility.md").exists()
    assert (reports_dir / "v3_phase0_combo.md").exists()
    assert (reports_dir / "v3_paper.md").exists()
    assert (reports_dir / "v3_listing_fade.md").exists()
