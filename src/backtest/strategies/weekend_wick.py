from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class WeekendWickStrategy:
    config = StrategyConfig(
        name="weekend_wick",
        leverage_cap=7.0,
        risk_per_trade_R=0.15,
        universe_fn=static_universe([]),
        bar_freq="1h",
        is_event_driven=False,
        metadata={"edge": "D"},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {"kline": ["open", "high", "low", "close", "volume", "wick_z"]}

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        if market_data.empty or len(market_data) < 2:
            return pd.DataFrame()

        signals: list[dict[str, object]] = []
        for idx in range(1, len(market_data)):
            row = market_data.iloc[idx]
            ts = market_data.index[idx]
            if ts.weekday() not in {5, 6}:
                continue
            if float(row.get("volume", 0.0)) < 5_000_000:
                continue
            if float(row.get("wick_z", 0.0)) < 2.5:
                continue

            prev_close = float(market_data.iloc[idx - 1]["close"])
            entry_price = float(row["close"])
            direction = -1 if entry_price > prev_close else 1
            stop_distance = max(float(row["high"] - row["low"]) * 0.25, entry_price * 0.01)
            stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
            target_price = prev_close
            signals.append(
                {
                    "entry_ts": ts,
                    "valid_until_ts": market_data.index[min(idx + 1, len(market_data) - 1)],
                    "signal": direction,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                }
            )

        return pd.DataFrame(signals)
