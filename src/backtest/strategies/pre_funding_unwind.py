from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class PreFundingUnwindStrategy:
    config = StrategyConfig(
        name="pre_funding_unwind",
        leverage_cap=8.0,
        risk_per_trade_R=0.18,
        universe_fn=static_universe([]),
        bar_freq="10m",
        is_event_driven=False,
        metadata={"edge": "E"},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {
            "kline": ["close", "high", "low", "quote_volume"],
            "funding": ["funding_rate", "next_funding_time"],
            "oi": ["oi_value"],
        }

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        if market_data.empty or len(market_data) < 5:
            return pd.DataFrame()

        frame = market_data.copy()
        funding_history = frame["funding_rate"].shift(1)
        frame["funding_mean"] = funding_history.rolling(100, min_periods=50).mean()
        frame["funding_std"] = funding_history.rolling(100, min_periods=50).std(ddof=0)
        frame["funding_z"] = (frame["funding_rate"] - frame["funding_mean"]) / frame["funding_std"].replace(0, pd.NA)
        frame["oi_ratio"] = frame["oi_value"] / frame["quote_volume"].replace(0, pd.NA)
        oi_history = frame["oi_ratio"].shift(1)
        frame["oi_mean"] = oi_history.rolling(5, min_periods=5).mean()
        frame["oi_std"] = oi_history.rolling(5, min_periods=5).std(ddof=0)
        frame["oi_z"] = (frame["oi_ratio"] - frame["oi_mean"]) / frame["oi_std"].replace(0, pd.NA)
        frame["price_delta"] = frame["close"] - frame["close"].shift(3)

        signals: list[dict[str, object]] = []
        for idx in range(5, len(frame)):
            row = frame.iloc[idx]
            funding_time = row.get("next_funding_time")
            if pd.isna(funding_time):
                continue

            now = frame.index[idx]
            minutes_to_settlement = (pd.Timestamp(funding_time) - now).total_seconds() / 60.0
            if minutes_to_settlement < 5 or minutes_to_settlement > 60:
                continue

            funding_z = row.get("funding_z")
            oi_z = row.get("oi_z")
            price_delta = row.get("price_delta")
            if pd.isna(funding_z) or pd.isna(oi_z) or pd.isna(price_delta):
                continue
            if abs(float(funding_z)) < 1.8:
                continue
            if float(oi_z) < 1.0:
                continue
            if float(funding_z) > 0 and float(price_delta) >= 0:
                continue
            if float(funding_z) < 0 and float(price_delta) <= 0:
                continue

            direction = -1 if float(funding_z) > 0 else 1
            entry_price = float(row["close"])
            stop_distance = max(float(row["high"] - row["low"]), entry_price * 0.01)
            stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
            target_price = entry_price - stop_distance if direction < 0 else entry_price + stop_distance
            valid_until_ts = min(pd.Timestamp(funding_time) + pd.Timedelta(minutes=30), frame.index[-1])
            signals.append(
                {
                    "entry_ts": now,
                    "valid_until_ts": valid_until_ts,
                    "signal": direction,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                }
            )

        return pd.DataFrame(signals)
