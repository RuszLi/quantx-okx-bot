import pandas as pd

from src.live.runner import LiveRunner


def test_live_runner_rejects_live_when_halted():
    runner = LiveRunner()
    runner.risk_guard.is_halted = True

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

    assert result.empty
