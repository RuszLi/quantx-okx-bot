import pandas as pd

from src.backtest.strategies.base import StrategyConfig, static_universe


def test_static_universe_returns_copy():
    universe = static_universe(["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    first = universe(pd.Timestamp("2026-06-25", tz="UTC"))
    second = universe(None)

    assert first == ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    assert second == ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    assert first is not second


def test_strategy_config_keeps_metadata():
    config = StrategyConfig(
        name="listing_fade",
        leverage_cap=5.0,
        risk_per_trade_R=0.30,
        universe_fn=static_universe(["DOGE-USDT-SWAP"]),
        bar_freq="1m",
        is_event_driven=True,
        metadata={"priority": "A"},
    )

    assert config.name == "listing_fade"
    assert config.metadata["priority"] == "A"
