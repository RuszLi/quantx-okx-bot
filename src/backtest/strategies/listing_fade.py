from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class ListingFadeStrategy:
    config = StrategyConfig(
        name="listing_fade",
        leverage_cap=5.0,
        risk_per_trade_R=0.30,
        universe_fn=static_universe([]),
        bar_freq="1m",
        is_event_driven=True,
        metadata={"edge": "A"},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {
            "kline": ["open", "high", "low", "close", "volume"],
            "events": ["announcement_id", "inst_id", "listing_time"],
        }

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        if external_events is None or external_events.empty or market_data.empty or len(market_data) < 6:
            return pd.DataFrame()

        first_bar = market_data.iloc[0]
        opening_price = float(first_bar["open"])
        pump_window = market_data.iloc[:5]
        pump_high = float(pump_window["high"].max())
        pump_ratio = pump_high / opening_price if opening_price else 0.0
        if pump_ratio < 1.15:
            return pd.DataFrame()

        volumes = pump_window["volume"].astype(float)
        pullback_idx = None
        for idx in range(5, len(market_data)):
            row = market_data.iloc[idx]
            price = float(row["close"])
            if pump_high * 0.85 <= price <= pump_high * 0.88 and float(row["volume"]) <= volumes.mean() * 0.5:
                pullback_idx = idx
                break

        if pullback_idx is None:
            return pd.DataFrame()

        row = market_data.iloc[pullback_idx]
        event = external_events.iloc[0]
        entry_price = float(row["close"])
        target_price = float(opening_price)
        stop_price = float(pump_high * 1.02)
        exit_idx = min(pullback_idx + 5, len(market_data) - 1)

        return pd.DataFrame(
            [
                {
                    "event_id": event["announcement_id"],
                    "symbol": event["inst_id"],
                    "entry_ts": market_data.index[pullback_idx],
                    "exit_ts": market_data.index[exit_idx],
                    "signal": -1,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "exit_price": float(market_data.iloc[exit_idx]["close"]),
                    "exit_reason": "TIME",
                    "risk_fraction": self.config.risk_per_trade_R,
                }
            ]
        )
