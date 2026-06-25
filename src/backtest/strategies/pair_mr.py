from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class PairMRStrategy:
    config = StrategyConfig(
        name="pair_mr",
        leverage_cap=10.0,
        risk_per_trade_R=0.15,
        universe_fn=static_universe([]),
        bar_freq="1h",
        is_event_driven=False,
        metadata={"edge": "K"},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {
            "kline": [
                "price_a",
                "price_b",
                "bucket_momentum_pct",
                "volume_a_24h",
                "volume_b_24h",
                "pair_eligible",
            ]
        }

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        if market_data.empty or len(market_data) < 5:
            return pd.DataFrame()

        frame = market_data.copy()
        frame["ratio"] = (frame["price_a"] / frame["price_b"].replace(0, pd.NA)).astype(float)
        ratio_history = frame["ratio"].shift(1)
        frame["ratio_mean"] = ratio_history.rolling(5, min_periods=5).mean()
        frame["ratio_std"] = ratio_history.rolling(5, min_periods=5).std(ddof=0)
        frame["ratio_z"] = (frame["ratio"] - frame["ratio_mean"]) / frame["ratio_std"].replace(0, pd.NA)

        signals: list[dict[str, object]] = []
        for idx in range(5, len(frame)):
            row = frame.iloc[idx]
            if not bool(row.get("pair_eligible", False)):
                continue
            if abs(float(row.get("bucket_momentum_pct", 1.0))) > 0.50:
                continue
            if float(row.get("volume_a_24h", 0.0)) < 5_000_000:
                continue
            if float(row.get("volume_b_24h", 0.0)) < 5_000_000:
                continue
            if pd.isna(row.get("ratio_z")) or abs(float(row["ratio_z"])) < 2.0:
                continue

            direction = -1 if float(row["ratio_z"]) > 0 else 1
            entry_price = float(row["ratio"])
            stop_distance = max(abs(float(row["ratio"] - row["ratio_mean"])), entry_price * 0.02)
            stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
            target_price = float(row["ratio_mean"])
            signals.append(
                {
                    "entry_ts": frame.index[idx],
                    "valid_until_ts": frame.index[min(idx + 2, len(frame) - 1)],
                    "signal": direction,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "meta": {
                        "leg_a": "SHORT" if direction < 0 else "LONG",
                        "leg_b": "LONG" if direction < 0 else "SHORT",
                    },
                }
            )

        return pd.DataFrame(signals)
