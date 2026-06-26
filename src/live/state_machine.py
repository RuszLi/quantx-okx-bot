from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class CriticalStrikeStateMachine:
    initial_equity: float = 7.0
    state: str = "audit-revision"
    equity: float = field(init=False)
    consecutive_losses: int = 0
    max_consecutive_losses_for_cooldown: int = 3
    cooldown_minutes: int = 30
    cooldown_until: pd.Timestamp | None = None
    audited: bool = False
    research_approved: bool = False

    VALID_STATES = [
        "audit-revision",
        "approved-for-research",
        "paper-live",
        "approved-for-gated-live",
        "halted",
    ]

    def __post_init__(self) -> None:
        self.equity = float(self.initial_equity)

    def mark_audited(self) -> None:
        self.audited = True

    def mark_approved_for_research(self) -> None:
        self.research_approved = True
        if self.audited and self.state == "audit-revision":
            self.state = "approved-for-research"

    def mark_paper_live(self) -> None:
        if self.state in ("audit-revision", "approved-for-research"):
            self.state = "paper-live"

    def can_enter_live(self) -> bool:
        return self.state == "approved-for-gated-live" and self.cooldown_until is None

    def can_run_paper(self) -> bool:
        return self.state in ("approved-for-research", "paper-live", "approved-for-gated-live")

    def record_trade_result(self, pnl_r: float, timestamp: pd.Timestamp) -> None:
        if pnl_r >= 0:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

        if pnl_r >= 3.0 and self.state == "approved-for-research":
            self.state = "approved-for-gated-live"

        if self.consecutive_losses >= self.max_consecutive_losses_for_cooldown:
            self.cooldown_until = timestamp + pd.Timedelta(minutes=self.cooldown_minutes)
