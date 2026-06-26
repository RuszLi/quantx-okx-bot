from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskGuard:
    daily_max_drawdown_pct: float = 0.15
    max_consecutive_losses: int = 3
    max_daily_trades: int = 5
    anchor_equity: float | None = None
    current_equity: float | None = None
    is_halted: bool = False
    consecutive_losses: int = 0
    daily_trades: int = 0
    halted_by: str | None = None

    def update_equity(self, equity: float, trade_pnl_r: float | None = None) -> None:
        if self.anchor_equity is None:
            self.anchor_equity = float(equity)
        self.current_equity = float(equity)

        if trade_pnl_r is not None:
            if trade_pnl_r >= 0:
                self.consecutive_losses = 0
            else:
                self.consecutive_losses += 1
            self.daily_trades += 1

        if self.anchor_equity > 0 and self.current_equity <= self.anchor_equity * (1.0 - self.daily_max_drawdown_pct):
            self.is_halted = True
            self.halted_by = "max_drawdown"

        if self.consecutive_losses >= self.max_consecutive_losses:
            self.is_halted = True
            self.halted_by = "consecutive_losses"

        if self.daily_trades >= self.max_daily_trades:
            self.is_halted = True
            self.halted_by = "max_daily_trades"

    def reset_day(self, equity: float) -> None:
        self.anchor_equity = float(equity)
        self.current_equity = float(equity)
        self.is_halted = False
        self.halted_by = None
        self.consecutive_losses = 0
        self.daily_trades = 0

    def can_trade(self) -> bool:
        return not self.is_halted
