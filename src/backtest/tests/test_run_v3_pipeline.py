import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_run_v3_pipeline_orchestrates_existing_dirs(tmp_path: Path):
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
    (probe_dir / "probe_payload.json").write_text(json.dumps({"instruments": {"ok": True, "count": 1}, "announcements": {"ok": True, "count": 1}, "candles": {"ok": True, "gap_pct": 0.0}, "funding": {"ok": True, "count": 1}, "oi": {"ok": True, "count": 1}}), encoding="utf-8")
    (probe_dir / "instrument_payload.json").write_text(json.dumps([{"instId": "BTC-USDT-SWAP", "minSz": "0.01", "lotSz": "0.01", "tickSz": "0.1", "ctVal": "0.01", "maxLeverage": "10"}]), encoding="utf-8")

    reports_dir = tmp_path / "reports"
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[3]
    env["PYTHONPATH"] = str(repo_root)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.reports.run_v3_pipeline",
            "--strategy-names",
            "listing_fade",
            "--start",
            "2026-06-25",
            "--end",
            "2026-06-25",
            "--skip-batch-run",
            "--backtests-dir",
            str(backtests_dir),
            "--probe-payload-json",
            str(probe_dir / "probe_payload.json"),
            "--instrument-payload-json",
            str(probe_dir / "instrument_payload.json"),
            "--probe-out-dir",
            str(probe_dir / "out"),
            "--reports-dir",
            str(reports_dir),
        ],
        check=True,
        cwd=tmp_path,
        env=env,
    )

    assert (reports_dir / "v3_api_signoff.md").exists()
    assert (reports_dir / "v3_listing_fade.md").exists()
