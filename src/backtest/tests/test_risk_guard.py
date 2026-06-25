from src.live.risk_guard import RiskGuard


def test_risk_guard_halts_after_daily_drawdown_limit():
    guard = RiskGuard(daily_max_drawdown_pct=0.5)
    assert guard.is_halted is False

    guard.update_equity(7.0)
    guard.update_equity(3.4)

    assert guard.is_halted is True
