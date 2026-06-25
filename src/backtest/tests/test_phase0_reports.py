from pathlib import Path

import pandas as pd

from src.reports.phase0 import write_phase0_strategy_report, write_phase0_combo_report


def test_write_phase0_strategy_report_contains_pass_fail_decision(tmp_path: Path):
    metrics = {
        "decision": "PASS",
        "win_rate": 0.58,
        "ev_R": 0.31,
        "profit_factor": 1.45,
        "max_consec_losses": 4,
    }
    out_path = tmp_path / "v3_B_funding_extreme.md"

    write_phase0_strategy_report("funding_extreme", metrics, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "funding_extreme" in text
    assert "DECISION: PASS" in text


def test_write_phase0_combo_report_lists_live_candidates(tmp_path: Path):
    summary = pd.DataFrame(
        [
            {"strategy_name": "listing_fade", "decision": "PASS", "ev_R": 0.45},
            {"strategy_name": "funding_extreme", "decision": "PASS", "ev_R": 0.32},
            {"strategy_name": "weekend_wick", "decision": "ABORT", "ev_R": -0.10},
        ]
    )
    out_path = tmp_path / "v3_phase0_combo.md"

    write_phase0_combo_report(summary, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "listing_fade" in text
    assert "funding_extreme" in text
    assert "live candidates" in text.lower()
