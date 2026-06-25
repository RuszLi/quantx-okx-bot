from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class FundingExtremeStrategy:
    config = StrategyConfig(
        name="funding_extreme",
        leverage_cap=8.0,
        risk_per_trade_R=0.20,
        universe_fn=static_universe([]),
        bar_freq="1h",
        is_event_driven=False,
        metadata={"edge": "B"},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {
            "kline": ["close", "high", "low", "quote_volume"],
            "funding": ["funding_rate"],
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
        frame["funding_mean"] = funding_history.rolling(5, min_periods=5).mean()
        frame["funding_std"] = funding_history.rolling(5, min_periods=5).std(ddof=0)
        frame["funding_z"] = (frame["funding_rate"] - frame["funding_mean"]) / frame["funding_std"].replace(0, pd.NA)
        frame["oi_ratio"] = frame["oi_value"] / frame["quote_volume"].replace(0, pd.NA)
        frame["oi_threshold"] = frame["oi_ratio"].shift(1).rolling(5, min_periods=5).quantile(0.8)
        frame["price_1h_return"] = frame["close"].pct_change()

        signals: list[dict[str, object]] = []
        for idx in range(5, len(frame)):
            row = frame.iloc[idx]
            funding_z = row.get("funding_z")
            oi_ratio = row.get("oi_ratio")
            oi_threshold = row.get("oi_threshold")
            price_ret = row.get("price_1h_return")

            if pd.isna(funding_z) or pd.isna(oi_ratio) or pd.isna(oi_threshold) or pd.isna(price_ret):
                continue
            if abs(float(funding_z)) < 2.0:
                continue
            if float(oi_ratio) <= float(oi_threshold):
                continue
            if float(funding_z) > 0 and float(price_ret) >= 0:
                continue
            if float(funding_z) < 0 and float(price_ret) <= 0:
                continue

            direction = -1 if float(funding_z) > 0 else 1
            entry_price = float(row["close"])
            stop_distance = max(float(row["high"] - row["low"]), entry_price * 0.015)
            stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
            target_price = entry_price - stop_distance if direction < 0 else entry_price + stop_distance
            valid_until_ts = frame.index[min(idx + 3, len(frame) - 1)]
            signals.append(
                {
                    "entry_ts": frame.index[idx],
                    "valid_until_ts": valid_until_ts,
                    "signal": direction,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                }
            )

        return pd.DataFrame(signals)
