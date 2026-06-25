from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskGuard:
    daily_max_drawdown_pct: float = 0.5
    anchor_equity: float | None = None
    current_equity: float | None = None
    is_halted: bool = False

    def update_equity(self, equity: float) -> None:
        if self.anchor_equity is None:
            self.anchor_equity = float(equity)
        self.current_equity = float(equity)
        if self.anchor_equity > 0 and self.current_equity <= self.anchor_equity * (1.0 - self.daily_max_drawdown_pct):
            self.is_halted = True

    def reset_day(self, equity: float) -> None:
        self.anchor_equity = float(equity)
        self.current_equity = float(equity)
        self.is_halted = False
