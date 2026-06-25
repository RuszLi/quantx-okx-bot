from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EventExecParams:
    fee_maker_per_side: float = 0.0002
    fee_taker_per_side: float = 0.0005
    slippage_per_side: float = 0.0010
    initial_equity: float = 7.0


def simulate_event_strategy(
    signals: pd.DataFrame,
    params: EventExecParams | None = None,
) -> pd.DataFrame:
    if params is None:
        params = EventExecParams()

    if signals.empty:
        return pd.DataFrame()

    trades: list[dict[str, object]] = []
    equity = float(params.initial_equity)

    for _, row in signals.iterrows():
        signal = int(row.get("signal", 0) or 0)
        entry_price = float(row.get("entry_price", np.nan) or np.nan)
        target_price = float(row.get("target_price", np.nan) or np.nan)
        stop_price = float(row.get("stop_price", np.nan) or np.nan)
        exit_price = float(row.get("exit_price", np.nan) or np.nan)
        entry_ts = row.get("entry_ts")
        exit_ts = row.get("exit_ts")
        exit_reason = str(row.get("exit_reason") or "UNKNOWN")

        if signal == 0 or np.isnan(entry_price) or np.isnan(exit_price) or np.isnan(stop_price):
            continue

        sign = float(signal)
        entry_fill = entry_price * (1.0 + params.slippage_per_side * sign)
        exit_fill = exit_price * (1.0 - params.slippage_per_side * sign)
        stop_distance_pct = abs(entry_price - stop_price) / entry_price if entry_price else np.nan
        if stop_distance_pct == 0 or np.isnan(stop_distance_pct):
            continue

        raw_ret = sign * (exit_fill - entry_fill) / entry_fill
        net_ret = raw_ret - params.fee_maker_per_side - params.fee_taker_per_side
        pnl_R = net_ret / stop_distance_pct
        equity += equity * float(row.get("risk_fraction", 0.0) or 0.0) * pnl_R

        trades.append(
            {
                "event_id": row.get("event_id"),
                "symbol": row.get("symbol"),
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "side": "LONG" if signal > 0 else "SHORT",
                "entry_price": entry_price,
                "target_price": target_price,
                "stop_price": stop_price,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "risk_fraction": float(row.get("risk_fraction", 0.0) or 0.0),
                "pnl_R": pnl_R,
                "equity_after": equity,
            }
        )

    return pd.DataFrame(trades)
