from pathlib import Path

import pandas as pd

from src.backtest.report_writer import write_strategy_report, write_paper_report


def test_write_strategy_report_persists_decision_markdown(tmp_path: Path):
    metrics = {
        "decision": "PASS",
        "win_rate": 0.60,
        "ev_R": 0.45,
        "profit_factor": 1.6,
        "n_trades": 50,
    }
    out_path = tmp_path / "v3_A_listing_fade.md"

    write_strategy_report("listing_fade", metrics, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "DECISION: PASS" in text
    assert "listing_fade" in text


def test_write_paper_report_summarizes_frequency_and_slippage(tmp_path: Path):
    trades = pd.DataFrame(
        [
            {"strategy_name": "listing_fade", "pnl_R": 0.5, "mode": "paper"},
            {"strategy_name": "funding_extreme", "pnl_R": -0.2, "mode": "paper"},
        ]
    )
    out_path = tmp_path / "v3_paper.md"

    write_paper_report(trades, out_path, slippage_bps=3.0)

    text = out_path.read_text(encoding="utf-8")
    assert "Paper Trading Report" in text
    assert "slippage_bps" in text
