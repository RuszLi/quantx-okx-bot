from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class EnsembleStrategy:
    priority: dict[str, int] = field(
        default_factory=lambda: {
            "listing_fade": 100,
            "funding_extreme": 90,
            "pre_funding_unwind": 85,
            "beta_decouple": 80,
            "weekend_wick": 70,
            "pair_mr": 60,
            "oi_velocity": 50,
        }
    )

    def resolve_conflicts(self, signals: pd.DataFrame, available_equity: float) -> pd.DataFrame:
        if signals.empty:
            return pd.DataFrame(columns=signals.columns)

        ranked = signals.copy()
        ranked["priority"] = ranked["strategy_name"].map(self.priority).fillna(0)
        ranked = ranked.sort_values(["entry_ts", "priority"], ascending=[True, False])

        winners = []
        for _, group in ranked.groupby(["entry_ts", "symbol"], sort=False):
            winners.append(group.iloc[0].drop(labels=["priority"]))
        return pd.DataFrame(winners).reset_index(drop=True)
