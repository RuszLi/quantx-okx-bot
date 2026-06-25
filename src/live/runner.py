from __future__ import annotations

import pandas as pd

from .risk_guard import RiskGuard
from .state_machine import CriticalStrikeStateMachine


class LiveRunner:
    def __init__(self) -> None:
        self.state_machine = CriticalStrikeStateMachine()
        self.risk_guard = RiskGuard()

    def run(self, signals: pd.DataFrame) -> pd.DataFrame:
        if signals.empty or self.risk_guard.is_halted:
            return pd.DataFrame()

        result = signals.copy()
        result["mode"] = "live"
        result["status"] = "queued"
        return result
