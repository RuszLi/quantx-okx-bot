"""Funding-family generator — parameterised signal generators for funding-rate strategies.

Exposes a ``FundingGenerator`` that produces ``Strategy``-satisfying classes
with configurable parameters (z-score threshold, R/R ratio, regime quantiles, …).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.backtest.strategies.base import StrategyConfig, static_universe


class FundingGenerator:
    """Generator for funding-rate based strategies.

    Usage::

        gen = FundingGenerator()
        params = {
            "z_score_threshold": 2.0,
            "r_to_r": 5.0,
            "stop_distance_pct": 0.003,
            "time_stop_bars": 12,
            "rv_window": 4,
            "regime_quantile_low": 0.40,
            "regime_quantile_high": 0.70,
            "funding_window": 720,
        }
        strategy_class = gen.generate(params)
    """

    def __init__(self) -> None:
        self._family_name = "funding"

    @property
    def family_name(self) -> str:
        return self._family_name

    def default_search_space(self) -> dict[str, list[Any]]:
        return {
            "z_score_threshold": [1.5, 2.0, 2.5, 3.0],
            "r_to_r": [3.0, 4.0, 5.0, 6.0],
            "stop_distance_pct": [0.002, 0.003, 0.005],
            "time_stop_bars": [8, 12, 16],
            "rv_window": [3, 4, 6],
            "regime_quantile_low": [0.30, 0.40, 0.50],
            "regime_quantile_high": [0.60, 0.70, 0.80],
            "funding_window": [480, 720, 960],
        }

    def required_data(self) -> list[str]:
        return ["klines", "funding_rate"]

    def generate(self, params: dict[str, Any]) -> type:
        """Create a parameterised funding-switch strategy class.

        Returns a **class** (not an instance) that satisfies the
        ``Strategy`` Protocol, with its ``config`` and
        ``compute_signals`` wired from *params*.
        """
        zt = float(params.get("z_score_threshold", 2.0))
        rr = float(params.get("r_to_r", 5.0))
        sd = float(params.get("stop_distance_pct", 0.003))
        ts = int(params.get("time_stop_bars", 12))
        rv_win = int(params.get("rv_window", 4))
        q_low = float(params.get("regime_quantile_low", 0.40))
        q_high = float(params.get("regime_quantile_high", 0.70))
        f_win = int(params.get("funding_window", 720))

        class _ParamFundingSwitch:
            """Parameterized variant of the funding-switch strategy."""

            config = StrategyConfig(
                name=f"funding_z_{zt}_rr_{rr}",
                leverage_cap=8.0,
                risk_per_trade_R=0.20,
                universe_fn=static_universe(["BTCUSDT"]),
                bar_freq="1h",
                is_event_driven=False,
                metadata={
                    "edge": "P",
                    "time_stop_bars": ts,
                    "generator": "funding",
                    "params": params,
                },
            )

            def required_data(self) -> dict[str, list[str]]:
                return {
                    "kline": ["open", "high", "low", "close", "quote_volume"],
                    "funding": ["funding_rate"],
                }

            def compute_signals(
                self,
                market_data: pd.DataFrame,
                external_events: pd.DataFrame | None = None,
            ) -> pd.DataFrame:
                if market_data.empty or len(market_data) < f_win:
                    return pd.DataFrame()

                frame = market_data.copy()

                # Realised volatility (rolling window = rv_win hours)
                returns = frame["close"].pct_change()
                frame["rv"] = returns.rolling(rv_win, min_periods=rv_win).std(ddof=0)

                # RV regime quantiles (rolling window = f_win ~30 days)
                frame["rv_q_low"] = frame["rv"].rolling(f_win, min_periods=max(f_win // 2, rv_win)).quantile(q_low)
                frame["rv_q_high"] = frame["rv"].rolling(f_win, min_periods=max(f_win // 2, rv_win)).quantile(q_high)

                # Funding z-score
                frame["funding_mean"] = frame["funding_rate"].rolling(f_win, min_periods=max(f_win // 2, 1)).mean()
                frame["funding_std"] = frame["funding_rate"].rolling(f_win, min_periods=max(f_win // 2, 1)).std(ddof=0)
                frame["funding_z"] = (frame["funding_rate"] - frame["funding_mean"]) / frame["funding_std"].replace(0, np.nan)

                # Regime detection with hysteresis
                regime: str = "NEUTRAL"
                regimes: list[str] = []
                for idx in range(len(frame)):
                    rv = frame["rv"].iloc[idx]
                    rv_low = frame["rv_q_low"].iloc[idx]
                    rv_high = frame["rv_q_high"].iloc[idx]

                    if pd.isna(rv) or pd.isna(rv_low) or pd.isna(rv_high):
                        regimes.append(regime)
                        continue

                    if regime == "NEUTRAL":
                        if rv < rv_low:
                            regime = "LOW"
                        elif rv > rv_high:
                            regime = "HIGH"
                    elif regime == "LOW":
                        if rv > rv_high:
                            regime = "HIGH"
                    elif regime == "HIGH":
                        if rv < rv_low:
                            regime = "LOW"
                    regimes.append(regime)

                frame["regime"] = regimes

                # Generate signals
                signals: list[dict[str, object]] = []
                for idx in range(f_win, len(frame)):
                    row = frame.iloc[idx]
                    fz = row.get("funding_z")
                    rs = row.get("regime")

                    if pd.isna(fz) or rs == "NEUTRAL":
                        continue
                    if abs(float(fz)) < zt:
                        continue

                    direction: int | None = None
                    if rs == "LOW":
                        direction = -1 if float(fz) > 0 else 1  # reversal
                    elif rs == "HIGH":
                        direction = 1 if float(fz) > 0 else -1   # follow

                    if direction is None:
                        continue

                    entry_price = float(row["close"])
                    stop_dist = entry_price * sd
                    stop_price = entry_price + stop_dist if direction < 0 else entry_price - stop_dist
                    target_price = entry_price - rr * stop_dist if direction < 0 else entry_price + rr * stop_dist
                    valid_until = frame.index[min(idx + ts, len(frame) - 1)]

                    signals.append({
                        "entry_ts": frame.index[idx],
                        "valid_until_ts": valid_until,
                        "signal": direction,
                        "entry_price": entry_price,
                        "target_price": target_price,
                        "stop_price": stop_price,
                    })

                return pd.DataFrame(signals)

        return _ParamFundingSwitch
