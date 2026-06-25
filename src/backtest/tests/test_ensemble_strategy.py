import pandas as pd

from src.backtest.strategies.ensemble import EnsembleStrategy


def test_ensemble_prioritizes_listing_fade_over_lower_priority_signals():
    signals = pd.DataFrame(
        [
            {
                "strategy_name": "funding_extreme",
                "symbol": "BTC-USDT-SWAP",
                "entry_ts": pd.Timestamp("2026-06-25T00:00:00Z"),
                "signal": -1,
                "entry_price": 100.0,
            },
            {
                "strategy_name": "listing_fade",
                "symbol": "BTC-USDT-SWAP",
                "entry_ts": pd.Timestamp("2026-06-25T00:00:00Z"),
                "signal": -1,
                "entry_price": 101.0,
            },
        ]
    )

    strategy = EnsembleStrategy()
    result = strategy.resolve_conflicts(signals, available_equity=7.0)

    assert len(result) == 1
    assert result.iloc[0]["strategy_name"] == "listing_fade"


def test_ensemble_skips_signals_when_equity_below_minimum():
    signals = pd.DataFrame(
        [
            {
                "strategy_name": "listing_fade",
                "symbol": "BTC-USDT-SWAP",
                "entry_ts": pd.Timestamp("2026-06-25T00:00:00Z"),
                "signal": -1,
                "entry_price": 101.0,
            }
        ]
    )

    strategy = EnsembleStrategy(min_equity=10.0)
    result = strategy.resolve_conflicts(signals, available_equity=7.0)

    assert result.empty
