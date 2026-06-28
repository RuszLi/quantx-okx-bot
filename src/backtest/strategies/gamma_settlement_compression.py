from __future__ import annotations

import pandas as pd

from .base import StrategyConfig, static_universe


class GammaSettlementCompressionStrategy:
    """Gamma (SC): settlement compression + post-settlement volatility release.

    核心假设：结算前 price range 压缩 → 结算后押注波动率释放。
    - 结算前 30min 观察 5m bar 的 range
    - 压缩判定：当前 range < 同时段（最近 N 个结算窗口）median range 的 50%
    - 方向：由 funding 符号决定（正 funding → 结算后 short，负 funding → long）
    - 趋势过滤：结算前价格动量方向与 funding 方向一致时过滤（避免押注失败）
    """

    config = StrategyConfig(
        name="gamma_settlement_compression",
        leverage_cap=8.0,
        risk_per_trade_R=0.20,
        universe_fn=static_universe(["BTCUSDT"]),
        bar_freq="5m",
        is_event_driven=False,
        metadata={"edge": "G", "time_stop_bars": 12},
    )

    def required_data(self) -> dict[str, list[str]]:
        return {
            "kline": ["open", "high", "low", "close", "quote_volume"],
            "funding": ["funding_rate", "next_funding_time"],
        }

    def compute_signals(
        self,
        market_data: pd.DataFrame,
        external_events: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        if market_data.empty or len(market_data) < 200:
            return pd.DataFrame()

        frame = market_data.copy()
        frame["range"] = frame["high"] - frame["low"]

        # Build a history of pre-settlement ranges for compression baseline
        # Settlement occurs every 8h (00:00, 08:00, 16:00 UTC)
        # We look at bars within 30min before settlement
        frame["is_pre_settlement"] = False
        frame["settlement_slot"] = None  # type: ignore[assignment]

        for idx in range(len(frame)):
            ts = frame.index[idx]
            funding_time = frame["next_funding_time"].iloc[idx]
            if pd.isna(funding_time):
                continue
            ft = pd.Timestamp(funding_time)
            minutes_to = (ft - ts).total_seconds() / 60.0
            if 0 < minutes_to <= 30:
                frame.loc[frame.index[idx], "is_pre_settlement"] = True
                # Slot key: hour of settlement (0, 8, 16)
                frame.loc[frame.index[idx], "settlement_slot"] = ft.hour

        # Compute median pre-settlement range per slot over recent history (last 30 settlements)
        # Use expanding/rolling per slot
        slot_medians: dict[int, float] = {}
        signals: list[dict[str, object]] = []

        # First pass: collect all pre-settlement ranges per slot
        pre_ranges: dict[int, list[tuple[pd.Timestamp, float]]] = {0: [], 8: [], 16: []}
        for idx in range(len(frame)):
            if frame["is_pre_settlement"].iloc[idx]:
                slot = frame["settlement_slot"].iloc[idx]
                if pd.isna(slot):
                    continue
                slot = int(slot)
                if slot in pre_ranges:
                    pre_ranges[slot].append((frame.index[idx], float(frame["range"].iloc[idx])))

        # Second pass: generate signals
        for idx in range(len(frame)):
            ts = frame.index[idx]
            funding_time = frame["next_funding_time"].iloc[idx]
            if pd.isna(funding_time):
                continue

            ft = pd.Timestamp(funding_time)
            minutes_to = (ft - ts).total_seconds() / 60.0
            if minutes_to < 5 or minutes_to > 30:
                continue

            # Must be within pre-settlement window
            current_range = float(frame["range"].iloc[idx])
            slot = ft.hour

            # Build rolling median for this slot from history up to this point
            history = [r for t, r in pre_ranges.get(slot, []) if t < ts]
            if len(history) < 10:
                continue
            median_range = pd.Series(history).median()
            if median_range <= 0:
                continue

            # Compression check: current range < 50% of median
            if current_range >= median_range * 0.5:
                continue

            funding_rate = float(frame["funding_rate"].iloc[idx])
            if abs(funding_rate) < 0.0001:  # require meaningful funding
                continue

            # Trend filter: price momentum in pre-settlement window
            # Look back up to 6 bars (30min) before current bar
            lookback_start = max(0, idx - 6)
            momentum = float(frame["close"].iloc[idx]) - float(frame["close"].iloc[lookback_start])

            # Direction: opposite of funding (bet on unwind after settlement)
            # If funding > 0 (longs pay shorts), expect post-settlement down move -> SHORT
            direction = -1 if funding_rate > 0 else 1

            # Trend filter: if momentum aligns with funding direction, skip
            # (e.g. funding > 0 and price already dropping -> good; funding > 0 and price rising -> skip)
            if funding_rate > 0 and momentum > 0:
                continue
            if funding_rate < 0 and momentum < 0:
                continue

            entry_price = float(frame["close"].iloc[idx])
            # Aggressive stop for higher hit-rate; 5:1 R/R
            stop_distance = entry_price * 0.003
            stop_price = entry_price + stop_distance if direction < 0 else entry_price - stop_distance
            target_price = entry_price - 5.0 * stop_distance if direction < 0 else entry_price + 5.0 * stop_distance
            valid_until_ts = frame.index[min(idx + 12, len(frame) - 1)]

            signals.append(
                {
                    "entry_ts": ts,
                    "valid_until_ts": valid_until_ts,
                    "signal": direction,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                }
            )

        return pd.DataFrame(signals)
