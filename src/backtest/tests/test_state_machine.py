import pandas as pd

from src.live.state_machine import CriticalStrikeStateMachine


def test_state_machine_transitions_through_alpha_and_cooldown():
    machine = CriticalStrikeStateMachine(initial_equity=7.0)

    assert machine.state == "audit-revision"
    assert machine.can_enter_live() is False

    machine.mark_audited()
    machine.mark_research_approved()
    assert machine.state == "approved-for-research"

    machine.record_trade_result(pnl_r=3.0, timestamp=pd.Timestamp("2026-06-25T00:00:00Z"))
    assert machine.state == "approved-for-gated-live"

    machine.record_trade_result(pnl_r=-1.0, timestamp=pd.Timestamp("2026-06-25T00:05:00Z"))
    machine.record_trade_result(pnl_r=-1.0, timestamp=pd.Timestamp("2026-06-25T00:06:00Z"))
    assert machine.cooldown_until is not None
