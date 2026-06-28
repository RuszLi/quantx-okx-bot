from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class AlphaFundingSwitchStrategy:
    """Alpha (FR-Switch): funding extreme with regime-aware hysteresis.

    Funding rate 的方向性预测力取决于波动率 regime：
    - 低波动 regime（RV < 40分位）→ funding extreme 反转
    - 高波动 regime（RV > 70分位）→ funding extreme 跟随
    - 40-70 分位之间保持上一 regime（hysteresis），避免频繁切换
    """

    config = StrategyConfig(
        name="alpha_funding_switch",
        leverage_cap=8.0,
        risk_per_trade_R=0.20,
        universe_fn=static_universe(["BTCUSDT"]),
        bar_freq="1h",
        is_event_driven=False,
        metadata={"edge": "A", "time_stop_bars": 12},
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
        if market_data.empty or len(market_data) < 720:
            return pd.DataFrame()

        frame = market_data.copy()

        # RV: 4-bar realized volatility (1h bars -> 4h window)
        returns = frame["close"].pct_change()
        frame["rv"] = returns.rolling(4, min_periods=4).std(ddof=0)

        # RV regime thresholds: 30-day rolling quantiles (720 bars)
        frame["rv_q40"] = frame["rv"].rolling(720, min_periods=360).quantile(0.40)
        frame["rv_q70"] = frame["rv"].rolling(720, min_periods=360).quantile(0.70)

        # Funding z-score: 30-day rolling
        frame["funding_mean"] = frame["funding_rate"].rolling(720, min_periods=360).mean()
        frame["funding_std"] = frame["funding_rate"].rolling(720, min_periods=360).std(ddof=0)
        frame["funding_z"] = (frame["funding_rate"] - frame["funding_mean"]) / frame["funding_std"].replace(0, pd.NA)

        # Regime with hysteresis
        regime = "NEUTRAL"
        regimes: list[str] = []
        for idx in range(len(frame)):
            rv = frame["rv"].iloc[idx]
            rv_q40 = frame["rv_q40"].iloc[idx]
            rv_q70 = frame["rv_q70"].iloc[idx]

            if pd.isna(rv) or pd.isna(rv_q40) or pd.isna(rv_q70):
                regimes.append(regime)
                continue

            if regime == "NEUTRAL":
                if rv < rv_q40:
                    regime = "LOW"
                elif rv > rv_q70:
                    regime = "HIGH"
            elif regime == "LOW":
                if rv > rv_q70:
                    regime = "HIGH"
                elif rv > rv_q40:
                    # stay LOW until cross mid-point (hysteresis)
                    pass
            elif regime == "HIGH":
                if rv < rv_q40:
                    regime = "LOW"
                elif rv < rv_q70:
                    # stay HIGH until cross mid-point
                    pass
            regimes.append(regime)

        frame["regime"] = regimes

        signals: list[dict[str, object]] = []
        for idx in range(720, len(frame)):
            row = frame.iloc[idx]
            funding_z = row.get("funding_z")
            regime_state = row.get("regime")

            if pd.isna(funding_z) or regime_state == "NEUTRAL":
                continue
            if abs(float(funding_z)) < 2.0:
                continue

            direction: int | None = None
            if regime_state == "LOW":
                # Low vol -> reversal
                direction = -1 if float(funding_z) > 0 else 1
            elif regime_state == "HIGH":
                # High vol -> follow
                direction = 1 if float(funding_z) > 0 else -1

            if direction is None:
                continue

            entry_price = float(row["close"])
            # Aggressive stop for higher hit-rate; 5:1 R/R
            stop_distance = entry_price * 0.003
            stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
            target_price = entry_price - 5.0 * stop_distance if direction < 0 else entry_price + 5.0 * stop_distance
            valid_until_ts = frame.index[min(idx + 12, len(frame) - 1)]

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
