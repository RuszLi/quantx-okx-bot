from src.backtest.strategies import STRATEGIES


def test_strategy_registry_exposes_v3_edges():
    assert "listing_fade" in STRATEGIES
    assert "funding_extreme" in STRATEGIES
    assert "pre_funding_unwind" in STRATEGIES
    assert "beta_decouple" in STRATEGIES
    assert "weekend_wick" in STRATEGIES
