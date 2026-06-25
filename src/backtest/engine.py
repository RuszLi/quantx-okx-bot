"""
engine.py — Phase 0 backtest event-driven simulation engine.
Simulates trades from features DataFrame, outputs trades.csv.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExecParams:
    fee_taker_per_side: float = 0.0005
    slippage_per_side: float = 0.0003
    time_stop_bars: int = 2
    risk_per_trade_pct: float = 0.20
    leverage: float = 12.0
    initial_equity: float = 7.0
    cooldown_after_loss_bars: int = 30
    daily_max_drawdown_pct: float = 0.45


def simulate(features: pd.DataFrame, params: ExecParams | None = None) -> pd.DataFrame:
    if params is None:
        params = ExecParams()

    stop_distance_pct = 0.012  # fixed per spec §5.3
    trades: list[dict] = []
    state = "FLAT"
    equity = float(params.initial_equity)
    recent_losses: deque = deque(maxlen=2)
    cooldown_until: Optional[pd.Timestamp] = None
    daily_anchor_equity = equity
    daily_anchor_date = features.index[0].date() if len(features) > 0 else None
    halted_today = False

    entry_ts: Optional[pd.Timestamp] = None
    entry_bar_idx: Optional[int] = None
    entry_price: float = 0.0
    entry_signal: int = 0
    exit_price: float = 0.0

    n_bars = len(features)
    for bar_idx in range(n_bars):
        ts = features.index[bar_idx]
        row = features.iloc[bar_idx]

        # Daily anchor update
        if daily_anchor_date is not None and ts.date() != daily_anchor_date:
            daily_anchor_equity = equity
            daily_anchor_date = ts.date()
            halted_today = False

        # Daily DD halt
        if daily_anchor_equity > 0 and equity < daily_anchor_equity * (1.0 - params.daily_max_drawdown_pct):
            halted_today = True

        # Cooldown check
        if cooldown_until is not None and ts < cooldown_until:
            continue

        if state == "FLAT":
            signal = int(row.get("signal", 0) or 0)
            entry_px = float(row.get("entry_price", np.nan) or np.nan)

            if signal != 0 and not np.isnan(entry_px) and not halted_today:
                entry_ts = ts
                entry_bar_idx = bar_idx
                entry_price = entry_px
                entry_signal = signal
                state = "IN_TRADE"

        elif state == "IN_TRADE":
            target_px = float(features.iloc[entry_bar_idx].get("target_price", np.nan) or np.nan)
            stop_px = float(features.iloc[entry_bar_idx].get("stop_price", np.nan) or np.nan)
            if np.isnan(target_px) or np.isnan(stop_px):
                state = "FLAT"
                continue

            exit_reason = None
            exit_px = 0.0

            # Time stop
            bars_held = bar_idx - entry_bar_idx
            if bars_held >= params.time_stop_bars:
                exit_reason = "TIME"
                exit_px = float(row["close"]) if not pd.isna(row["close"]) else float(row["open"])

            # Check stop/target within this bar
            bar_high = float(row["high"])
            bar_low = float(row["low"])

            if entry_signal == +1:  # LONG: looking for price rally
                # Stop hit first (pessimistic: SL before TP in same bar)
                if bar_low <= stop_px and exit_reason is None:
                    exit_reason = "SL"
                    exit_px = stop_px
                elif bar_high >= target_px and exit_reason is None:
                    exit_reason = "TP"
                    exit_px = target_px
                # Time stop
                if exit_reason is None and bars_held >= params.time_stop_bars:
                    exit_reason = "TIME"
                    exit_px = float(row["close"]) if not pd.isna(row["close"]) else float(row["open"])
            else:  # SHORT: looking for price decline
                if bar_high >= stop_px and exit_reason is None:
                    exit_reason = "SL"
                    exit_px = stop_px
                elif bar_low <= target_px and exit_reason is None:
                    exit_reason = "TP"
                    exit_px = target_px
                if exit_reason is None and bars_held >= params.time_stop_bars:
                    exit_reason = "TIME"
                    exit_px = float(row["close"]) if not pd.isna(row["close"]) else float(row["open"])

            if exit_reason is None:
                continue  # still holding

            # PnL calculation (spec §5.3)
            sign = float(entry_signal)
            entry_fill = entry_price * (1.0 + params.slippage_per_side * sign)
            exit_fill = exit_px * (1.0 - params.slippage_per_side * sign)
            raw_ret = sign * (exit_fill - entry_fill) / entry_fill
            net_ret = raw_ret - 2.0 * params.fee_taker_per_side
            pnl_R = net_ret / stop_distance_pct
            equity_change = equity * params.risk_per_trade_pct * pnl_R
            equity += equity_change
            pnl_pct_equity = equity_change / (equity - equity_change) * 100.0 if (equity - equity_change) != 0 else 0.0

            is_loss = pnl_R < 0
            recent_losses.append(1 if is_loss else 0)

            trades.append({
                "entry_ts": entry_ts,
                "exit_ts": ts,
                "side": "LONG" if entry_signal == 1 else "SHORT",
                "entry_price": round(entry_price, 8),
                "exit_price": round(exit_px, 8),
                "target_price": round(target_px, 8),
                "stop_price": round(stop_px, 8),
                "exit_reason": exit_reason,
                "pnl_R": round(pnl_R, 6),
                "pnl_pct_equity": round(pnl_pct_equity, 4),
                "equity_after": round(equity, 6),
                "bars_held": bars_held,
            })

            # Cooldown after 2 consecutive losses
            if sum(recent_losses) == 2 and len(recent_losses) == 2:
                cooldown_until = ts + pd.Timedelta(minutes=params.cooldown_after_loss_bars)

            state = "FLAT"

    return pd.DataFrame(trades)
