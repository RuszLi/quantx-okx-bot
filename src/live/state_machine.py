from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class CriticalStrikeStateMachine:
    initial_equity: float = 7.0
    state: str = "audit-revision"
    equity: float = field(init=False)
    consecutive_losses: int = 0
    cooldown_until: pd.Timestamp | None = None
    audited: bool = False
    research_approved: bool = False

    def __post_init__(self) -> None:
        self.equity = float(self.initial_equity)

    def mark_audited(self) -> None:
        self.audited = True

    def mark_research_approved(self) -> None:
        self.research_approved = True
        if self.audited:
            self.state = "approved-for-research"

    def can_enter_live(self) -> bool:
        return self.state == "approved-for-gated-live" and self.cooldown_until is None

    def record_trade_result(self, pnl_r: float, timestamp: pd.Timestamp) -> None:
        if pnl_r >= 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        if pnl_r >= 3.0 and self.state == "approved-for-research":
            self.state = "approved-for-gated-live"

        if self.consecutive_losses >= 2:
            self.cooldown_until = timestamp + pd.Timedelta(minutes=30)
