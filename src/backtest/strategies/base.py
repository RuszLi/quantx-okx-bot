from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import pandas as pd


UniverseFn = Callable[[pd.Timestamp | None], list[str]]


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    leverage_cap: float
    risk_per_trade_R: float
    universe_fn: UniverseFn
    bar_freq: str
    is_event_driven: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class Strategy(Protocol):
    config: StrategyConfig

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        ...

    def required_data(self) -> dict[str, list[str]]:
        ...


def static_universe(symbols: list[str]) -> UniverseFn:
    frozen_symbols = list(symbols)

    def _universe(_: pd.Timestamp | None = None) -> list[str]:
        return list(frozen_symbols)

    return _universe
