from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class BetaDecoupleStrategy:
    config = StrategyConfig(
        name="beta_decouple",
        leverage_cap=10.0,
        risk_per_trade_R=0.20,
        universe_fn=static_universe([]),
        bar_freq="1h",
        is_event_driven=False,
        metadata={"edge": "C"},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {
            "kline": [
                "btc_close",
                "btc_return_60m",
                "btc_rv_pct",
                "alt_close",
                "alt_vwap_60m",
                "alt_volume_24h",
                "alt_age_days",
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
        frame["alt_deviation"] = frame["alt_close"] - frame["alt_vwap_60m"]
        deviation_history = frame["alt_deviation"].shift(1)
        frame["alt_deviation_mean"] = deviation_history.rolling(5, min_periods=5).mean()
        frame["alt_deviation_std"] = deviation_history.rolling(5, min_periods=5).std(ddof=0)
        frame["alt_z"] = (frame["alt_deviation"] - frame["alt_deviation_mean"]) / frame["alt_deviation_std"].replace(0, pd.NA)

        signals: list[dict[str, object]] = []
        for idx in range(5, len(frame)):
            row = frame.iloc[idx]
            if pd.isna(row.get("btc_rv_pct")) or pd.isna(row.get("alt_z")):
                continue
            if float(row["btc_rv_pct"]) >= 0.30:
                continue
            if abs(float(row["alt_z"])) < 2.0:
                continue
            if float(row.get("alt_volume_24h", 0.0)) < 10_000_000:
                continue
            if float(row.get("alt_age_days", 0.0)) < 30:
                continue

            direction = -1 if float(row["alt_z"]) > 0 else 1
            entry_price = float(row["alt_close"])
            stop_distance = max(abs(float(row["alt_deviation"])) * 0.25, entry_price * 0.015)
            stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
            target_price = entry_price - stop_distance if direction < 0 else entry_price + stop_distance
            signals.append(
                {
                    "entry_ts": frame.index[idx],
                    "valid_until_ts": frame.index[min(idx + 2, len(frame) - 1)],
                    "signal": direction,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                }
            )

        return pd.DataFrame(signals)
