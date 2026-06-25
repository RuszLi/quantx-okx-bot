from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class OIVelocityStrategy:
    config = StrategyConfig(
        name="oi_velocity",
        leverage_cap=10.0,
        risk_per_trade_R=0.18,
        universe_fn=static_universe([]),
        bar_freq="5m",
        is_event_driven=False,
        metadata={"edge": "H"},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {
            "kline": [
                "close",
                "high",
                "low",
                "oi_velocity_pct",
                "price_delta_pct",
                "burst_move_pct",
                "volume_decay_pct",
                "volume_24h",
            ]
        }

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        if market_data.empty or len(market_data) < 2:
            return pd.DataFrame()

        signals: list[dict[str, object]] = []
        preburst_active = False
        burst_seen = False
        burst_anchor_close: float | None = None

        for idx in range(len(market_data)):
            row = market_data.iloc[idx]
            if float(row.get("volume_24h", 0.0)) < 10_000_000:
                continue

            if float(row.get("oi_velocity_pct", 0.0)) >= 0.95 and float(row.get("price_delta_pct", 1.0)) <= 0.30:
                preburst_active = True

            if not preburst_active:
                continue

            if not burst_seen and float(row.get("burst_move_pct", 0.0)) >= 1.5:
                burst_seen = True
                burst_anchor_close = float(row["close"])
                continue
            if not burst_seen:
                continue
            if float(row.get("volume_decay_pct", 0.0)) < 0.30:
                continue
            if burst_anchor_close is not None and float(row["close"]) > burst_anchor_close:
                continue

            entry_price = float(row["close"])
            stop_distance = max(float(row["high"] - row["low"]) * 0.25, entry_price * 0.01)
            signals.append(
                {
                    "entry_ts": market_data.index[idx],
                    "valid_until_ts": market_data.index[min(idx + 2, len(market_data) - 1)],
                    "signal": -1,
                    "entry_price": entry_price,
                    "target_price": entry_price - stop_distance,
                    "stop_price": entry_price + stop_distance,
                }
            )

        return pd.DataFrame(signals)
