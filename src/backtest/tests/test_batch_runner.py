from pathlib import Path

import pandas as pd

from src.backtest.batch_runner import run_batch_strategies


def test_run_batch_strategies_writes_backtest_dirs(monkeypatch, tmp_path: Path):
    def fake_run_named_strategy(strategy_name, start, end, universe_path, out_dir):
        trades = pd.DataFrame(
            [
                {
                    "strategy_name": strategy_name,
                    "symbol": "BTCUSDT",
                    "entry_ts": pd.Timestamp("2026-06-25T00:00:00Z"),
                    "exit_ts": pd.Timestamp("2026-06-25T00:10:00Z"),
                    "signal": -1,
                    "entry_price": 100.0,
                    "target_price": 95.0,
                    "stop_price": 105.0,
                    "exit_price": 96.0,
                    "exit_reason": "TP",
                    "pnl_R": 0.8,
                    "equity_after": 7.5,
                }
            ]
        )
        summary = {"strategy_name": strategy_name, "signals": 1, "symbols": 1}
        return trades, summary

    monkeypatch.setattr("src.backtest.batch_runner.run_named_strategy", fake_run_named_strategy)

    outputs = run_batch_strategies(
        strategy_names=["listing_fade", "funding_extreme"],
        start=pd.Timestamp("2026-06-25").date(),
        end=pd.Timestamp("2026-06-25").date(),
        universe_path=None,
        backtests_dir=tmp_path / "backtests",
    )

    assert (tmp_path / "backtests" / "listing_fade" / "trades.csv").exists()
    assert (tmp_path / "backtests" / "funding_extreme" / "summary.json").exists()
    assert len(outputs) == 2
