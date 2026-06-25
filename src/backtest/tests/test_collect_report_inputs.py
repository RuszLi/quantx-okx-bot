from pathlib import Path

import pandas as pd

from src.reports.collect_inputs import collect_report_inputs


def test_collect_report_inputs_builds_strategy_metrics_and_combo_summary(tmp_path: Path):
    backtest_dir = tmp_path / "backtests"
    backtest_dir.mkdir()

    listing_dir = backtest_dir / "listing_fade"
    listing_dir.mkdir()
    funding_dir = backtest_dir / "funding_extreme"
    funding_dir.mkdir()

    pd.DataFrame([
        {"decision": "PASS", "win_rate": 0.60, "ev_R": 0.45, "profit_factor": 1.6, "max_consec_losses": 4, "n_trades": 50}
    ]).to_json(listing_dir / "summary.json", orient="records")
    pd.DataFrame([
        {"strategy_name": "listing_fade", "pnl_R": 0.5, "mode": "paper"},
        {"strategy_name": "listing_fade", "pnl_R": -0.2, "mode": "paper"},
    ]).to_csv(listing_dir / "trades.csv", index=False)

    pd.DataFrame([
        {"decision": "PASS", "win_rate": 0.56, "ev_R": 0.31, "profit_factor": 1.4, "max_consec_losses": 5, "n_trades": 80}
    ]).to_json(funding_dir / "summary.json", orient="records")
    pd.DataFrame([
        {"strategy_name": "funding_extreme", "pnl_R": 0.1, "mode": "paper"},
    ]).to_csv(funding_dir / "trades.csv", index=False)

    api_checks = {"instruments": {"status": "PASS", "evidence": "ok"}}
    execution_rows = [{"instId": "BTC-USDT-SWAP", "minSz": 0.01, "lotSz": 0.01, "tickSz": 0.1, "ctVal": 0.01, "can_open_position": True, "can_place_hard_stop": True, "can_post_only_fill": True}]

    inputs = collect_report_inputs(backtest_dir, api_checks=api_checks, execution_rows=execution_rows)

    assert "listing_fade" in inputs["strategy_metrics"]
    assert "funding_extreme" in inputs["strategy_metrics"]
    assert len(inputs["combo_summary"]) == 2
    assert len(inputs["paper_trades"]) == 3
