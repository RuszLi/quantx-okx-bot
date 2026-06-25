import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_orchestrate_v3_bundle_runs_end_to_end_with_stub_inputs(tmp_path: Path):
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

    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    (probe_dir / "api_checks.json").write_text(json.dumps({"instruments": {"status": "PASS", "evidence": "ok"}}), encoding="utf-8")
    (probe_dir / "execution_rows.json").write_text(json.dumps([{"instId": "BTC-USDT-SWAP", "minSz": 0.01, "lotSz": 0.01, "tickSz": 0.1, "ctVal": 0.01, "can_open_position": True, "can_place_hard_stop": True, "can_post_only_fill": True}]), encoding="utf-8")

    reports_dir = tmp_path / "reports"
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = str(repo_root)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.reports.orchestrate_v3_bundle",
            "--backtests-dir",
            str(backtests_dir),
            "--api-checks-json",
            str(probe_dir / "api_checks.json"),
            "--execution-rows-json",
            str(probe_dir / "execution_rows.json"),
            "--reports-dir",
            str(reports_dir),
        ],
        check=True,
        cwd=tmp_path,
        env=env,
    )

    assert (reports_dir / "v3_api_signoff.md").exists()
    assert (reports_dir / "v3_phase0_combo.md").exists()
