import pandas as pd

from src.backtest.event_engine import simulate_event_strategy


def test_simulate_event_strategy_generates_trade_rows():
    signals = pd.DataFrame(
        [
            {
                "event_id": "evt-1",
                "symbol": "DOGE-USDT-SWAP",
                "entry_ts": pd.Timestamp("2026-06-25T00:05:00Z"),
                "exit_ts": pd.Timestamp("2026-06-25T00:10:00Z"),
                "signal": -1,
                "entry_price": 1.0,
                "target_price": 0.92,
                "stop_price": 1.05,
                "exit_price": 0.95,
                "exit_reason": "TP",
                "risk_fraction": 0.30,
            }
        ]
    )

    trades = simulate_event_strategy(signals)

    assert len(trades) == 1
    assert trades.iloc[0]["side"] == "SHORT"
    assert trades.iloc[0]["pnl_R"] > 0
