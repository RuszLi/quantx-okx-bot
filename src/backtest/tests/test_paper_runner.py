import pandas as pd

from src.paper.runner import PaperRunner


def test_paper_runner_records_signals_without_live_side_effects():
    runner = PaperRunner()
    signals = pd.DataFrame(
        [
            {
                "strategy_name": "listing_fade",
                "symbol": "BTC-USDT-SWAP",
                "entry_ts": pd.Timestamp("2026-06-25T00:00:00Z"),
                "signal": -1,
                "entry_price": 100.0,
                "target_price": 95.0,
                "stop_price": 105.0,
            }
        ]
    )

    result = runner.run(signals)

    assert len(result) == 1
    assert result.iloc[0]["mode"] == "paper"
