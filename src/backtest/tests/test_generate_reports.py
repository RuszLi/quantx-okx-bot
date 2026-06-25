from pathlib import Path

import pandas as pd

from src.reports.generate import generate_all_reports


def test_generate_all_reports_writes_named_plan_outputs(tmp_path: Path):
    strategy_metrics = {
        "listing_fade": {"decision": "PASS", "ev_R": 0.45, "win_rate": 0.60},
        "funding_extreme": {"decision": "PASS", "ev_R": 0.31, "win_rate": 0.56},
    }
    combo_summary = pd.DataFrame(
        [
            {"strategy_name": "listing_fade", "decision": "PASS", "ev_R": 0.45},
            {"strategy_name": "funding_extreme", "decision": "PASS", "ev_R": 0.31},
        ]
    )
    paper_trades = pd.DataFrame(
        [
            {"strategy_name": "listing_fade", "pnl_R": 0.5, "mode": "paper"},
            {"strategy_name": "funding_extreme", "pnl_R": -0.2, "mode": "paper"},
        ]
    )
    api_checks = {"instruments": {"status": "PASS", "evidence": "ok"}}
    execution_rows = [
        {
            "instId": "BTC-USDT-SWAP",
            "minSz": 0.01,
            "lotSz": 0.01,
            "tickSz": 0.1,
            "ctVal": 0.01,
            "can_open_position": True,
            "can_place_hard_stop": True,
            "can_post_only_fill": True,
        }
    ]

    outputs = generate_all_reports(
        reports_dir=tmp_path,
        strategy_metrics=strategy_metrics,
        combo_summary=combo_summary,
        paper_trades=paper_trades,
        api_checks=api_checks,
        execution_rows=execution_rows,
        slippage_bps=3.0,
    )

    assert (tmp_path / "v3_api_signoff.md").exists()
    assert (tmp_path / "v3_execution_feasibility.md").exists()
    assert (tmp_path / "v3_phase0_combo.md").exists()
    assert (tmp_path / "v3_paper.md").exists()
    assert (tmp_path / "v3_listing_fade.md").exists()
    assert outputs["api_signoff"].name == "v3_api_signoff.md"
