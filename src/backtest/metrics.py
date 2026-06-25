"""
metrics.py — Phase 0 backtest summary computation.
Computes win_rate, ev_R, profit_factor, max_consec_losses, etc.
Outputs summary.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, n_symbols: int, n_days: int) -> dict[str, Any]:
    """Compute summary metrics from a trades DataFrame."""
    n_trades = len(trades)

    if n_trades == 0:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "ev_R": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "max_consec_losses": 0,
            "max_consec_wins": 0,
            "trades_per_day_per_symbol": 0.0,
            "avg_holding_bars": 0.0,
            "best_trade_R": 0.0,
            "worst_trade_R": 0.0,
            "by_symbol": {},
            "by_hour_utc": {},
            "exit_reason_breakdown": {"TP": 0, "SL": 0, "TIME": 0},
            "decision": "ABORT",
        }

    wins = trades[trades["pnl_R"] > 0]
    losses = trades[trades["pnl_R"] <= 0]
    win_rate = len(wins) / n_trades

    ev_R = trades["pnl_R"].mean()
    sum_wins = wins["pnl_R"].sum() if len(wins) > 0 else 0.0
    sum_losses = abs(losses["pnl_R"].sum()) if len(losses) > 0 else 1.0
    profit_factor = sum_wins / sum_losses if sum_losses > 0 else float("inf")

    # Max consecutive losses
    consec = 0
    max_consec_losses = 0
    max_consec_wins = 0
    consec_w = 0
    for _, r in trades["pnl_R"].items():
        if r < 0:
            consec += 1
            consec_w = 0
            max_consec_losses = max(max_consec_losses, consec)
        else:
            consec = 0
            consec_w += 1
            max_consec_wins = max(max_consec_wins, consec_w)

    # Drawdown from equity_after column
    if "equity_after" in trades.columns and len(trades) > 0:
        eq = trades["equity_after"].values
        peak = np.maximum.accumulate(eq)
        dd = np.where(peak > 0, (peak - eq) / peak, 0.0)
        max_dd_pct = float(np.max(dd)) * 100.0
    else:
        max_dd_pct = 0.0

    # Trades per day per symbol
    tps = n_trades / (n_symbols * n_days) if n_symbols > 0 and n_days > 0 else 0.0

    avg_holding = trades["bars_held"].mean() if "bars_held" in trades.columns else 0.0
    best = trades["pnl_R"].max()
    worst = trades["pnl_R"].min()

    # Breakdown by exit reason
    exit_breakdown = trades["exit_reason"].value_counts().to_dict()
    for k in ["TP", "SL", "TIME"]:
        exit_breakdown.setdefault(k, 0)

    # By symbol (handle if column exists)
    by_symbol = {}
    if "symbol" in trades.columns:
        for sym, grp in trades.groupby("symbol"):
            n = len(grp)
            wr = len(grp[grp["pnl_R"] > 0]) / n if n > 0 else 0.0
            ev = grp["pnl_R"].mean()
            by_symbol[str(sym)] = {"n": n, "wr": round(wr, 4), "ev_R": round(ev, 4)}

    # By hour UTC
    by_hour = {}
    if "entry_ts" in trades.columns:
        trades["hour"] = pd.to_datetime(trades["entry_ts"], utc=True).dt.hour
        for h, grp in trades.groupby("hour"):
            n = len(grp)
            wr = len(grp[grp["pnl_R"] > 0]) / n if n > 0 else 0.0
            ev = grp["pnl_R"].mean()
            by_hour[str(h)] = {"n": n, "wr": round(wr, 4), "ev_R": round(ev, 4)}

    # Decision gate (spec §5.4)
    if win_rate >= 0.55 and ev_R >= 0.3 and profit_factor >= 1.4 and tps >= 3 and max_consec_losses <= 6:
        decision = "PASS"
    elif 0.50 <= win_rate < 0.55:
        decision = "REPARAM"
    else:
        decision = "ABORT"

    return {
        "n_trades": n_trades,
        "win_rate": round(win_rate, 4),
        "ev_R": round(float(ev_R), 4),
        "profit_factor": round(float(profit_factor), 4),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_consec_losses": max_consec_losses,
        "max_consec_wins": max_consec_wins,
        "trades_per_day_per_symbol": round(tps, 4),
        "avg_holding_bars": round(avg_holding, 2),
        "best_trade_R": round(float(best), 4),
        "worst_trade_R": round(float(worst), 4),
        "by_symbol": by_symbol,
        "by_hour_utc": by_hour,
        "exit_reason_breakdown": {k: int(v) for k, v in exit_breakdown.items()},
        "decision": decision,
    }


def save_summary(summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
