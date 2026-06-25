import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_sample_inputs_cli_writes_expected_input_files(tmp_path: Path):
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

    out_dir = tmp_path / "inputs"
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = str(repo_root)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.reports.sample_inputs",
            "--backtests-dir",
            str(backtests_dir),
            "--api-checks-json",
            str(api_checks_path),
            "--execution-rows-json",
            str(execution_rows_path),
            "--out-dir",
            str(out_dir),
        ],
        check=True,
        cwd=tmp_path,
        env=env,
    )

    assert (out_dir / "strategy_metrics.json").exists()
    assert (out_dir / "combo_summary.csv").exists()
    assert (out_dir / "paper_trades.csv").exists()
