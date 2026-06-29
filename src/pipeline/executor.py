"""Executor — runs backtests for a list of candidates.

Phase 4 implementation: instantiates the candidate's strategy class (via the
matching generator), drives ``simulate()`` over the candidate-specific feature
frame, computes summary metrics, and runs a 3×3×3 sensitivity grid
(time_stop_bars × fee_mult × slippage_mult) to derive a robustness label.

The executor stays decoupled from the V3 orchestrator: it talks to
``src.backtest.engine.simulate`` directly through an injected ``features``
frame, so any callable that returns a Strategy-shaped object can be plugged in.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Literal

import numpy as np
import pandas as pd

from src.backtest.engine import ExecParams, simulate

from .candidate import Candidate

RobustnessLabel = Literal["HIGH", "MEDIUM", "LOW"]

# Sensitivity grid axes (Plan §Phase 4.4). 27 cells = 3 × 3 × 3.
_TIME_STOP_VARIANTS: tuple[int, int, int] = (1, 2, 4)
_FEE_MULTIPLIERS: tuple[float, float, float] = (0.8, 1.0, 1.5)
_SLIP_MULTIPLIERS: tuple[float, float, float] = (0.8, 1.0, 1.5)

# Robustness thresholds — fraction of grid cells with EV(R) > 0.
_ROBUSTNESS_HIGH_MIN = 18  # ≥ 18/27 ≈ 0.67
_ROBUSTNESS_MEDIUM_MIN = 12  # ≥ 12/27 ≈ 0.44

FeaturesBuilder = Callable[[Candidate, dict[str, pd.DataFrame]], pd.DataFrame]


def _max_consec_losses(pnl_R: pd.Series) -> int:
    consec = best = 0
    for r in pnl_R:
        if r < 0:
            consec += 1
            best = max(best, consec)
        else:
            consec = 0
    return best


def _profit_factor(pnl_R: pd.Series) -> float:
    wins = pnl_R[pnl_R > 0].sum()
    losses = -pnl_R[pnl_R < 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def _summarize(trades: pd.DataFrame) -> dict[str, Any]:
    if trades is None or trades.empty or "pnl_R" not in trades.columns:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "ev_R": 0.0,
            "profit_factor": 0.0,
            "max_consec_losses": 0,
            "avg_holding_bars": 0.0,
            "max_drawdown_R": 0.0,
        }
    pnl = trades["pnl_R"].astype(float)
    equity = pnl.cumsum()
    peak = equity.cummax()
    drawdown = (peak - equity).max() if len(equity) else 0.0
    return {
        "n_trades": int(len(trades)),
        "win_rate": float((pnl > 0).mean()),
        "ev_R": float(pnl.mean()),
        "profit_factor": _profit_factor(pnl),
        "max_consec_losses": _max_consec_losses(pnl),
        "avg_holding_bars": float(trades.get("bars_held", pd.Series([0])).mean()),
        "max_drawdown_R": float(drawdown),
    }


def _resolve_strategy(candidate: Candidate, generator_registry: dict[str, Any]) -> Any:
    """Instantiate the candidate's strategy.

    Resolution order:
      1. ``candidate.family`` matches a generator in ``generator_registry`` —
         call ``generator.generate(candidate.params)`` and instantiate.
      2. ``candidate.strategy_class`` matches a class name in any registered
         generator — used as a marker that the candidate was produced by that
         generator (current funding generator returns a class).
    """
    gen = generator_registry.get(candidate.family)
    if gen is None:
        raise KeyError(
            f"No generator registered for family {candidate.family!r}; "
            f"known: {sorted(generator_registry)}"
        )
    strategy_cls = gen.generate(candidate.params)
    return strategy_cls() if isinstance(strategy_cls, type) else strategy_cls


def _classify_robustness(grid: pd.DataFrame) -> RobustnessLabel:
    positives = int((grid["ev_R"] > 0).sum())
    if positives >= _ROBUSTNESS_HIGH_MIN:
        return "HIGH"
    if positives >= _ROBUSTNESS_MEDIUM_MIN:
        return "MEDIUM"
    return "LOW"


def _sensitivity_grid(features: pd.DataFrame, base_params: ExecParams) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ts_bars in _TIME_STOP_VARIANTS:
        for fee_m in _FEE_MULTIPLIERS:
            for slip_m in _SLIP_MULTIPLIERS:
                params = dataclasses.replace(
                    base_params,
                    time_stop_bars=ts_bars,
                    fee_taker_per_side=base_params.fee_taker_per_side * fee_m,
                    slippage_per_side=base_params.slippage_per_side * slip_m,
                )
                trades = simulate(features, params)
                summary = _summarize(trades)
                rows.append({
                    "time_stop_bars": ts_bars,
                    "fee_mult": fee_m,
                    "slip_mult": slip_m,
                    "n_trades": summary["n_trades"],
                    "win_rate": round(summary["win_rate"], 4),
                    "ev_R": round(summary["ev_R"], 6),
                    "profit_factor": round(summary["profit_factor"], 4)
                    if np.isfinite(summary["profit_factor"]) else float("inf"),
                })
    return pd.DataFrame(rows)


def _signals_to_features(signals: pd.DataFrame, market_data: pd.DataFrame) -> pd.DataFrame:
    """Project Strategy-emitted signal rows onto the bar grid expected by ``simulate``.

    Strategies in this project return one-row-per-signal frames keyed by
    ``entry_ts``; the backtest engine expects a continuous OHLC index with
    optional signal/entry/target/stop columns. This adapter aligns the two.
    """
    if signals is None or signals.empty:
        return pd.DataFrame()
    md = market_data.copy()
    if md.index.tz is None:
        md.index = pd.to_datetime(md.index, utc=True)
    sig = signals.copy()
    if "entry_ts" not in sig.columns:
        raise ValueError("signals frame missing required 'entry_ts' column")
    sig["entry_ts"] = pd.to_datetime(sig["entry_ts"], utc=True)
    sig = sig.drop_duplicates(subset=["entry_ts"]).set_index("entry_ts")
    aligned = md.join(sig[["signal", "entry_price", "target_price", "stop_price"]], how="left")
    aligned["signal"] = aligned["signal"].fillna(0).astype(int)
    for col in ("entry_price", "target_price", "stop_price"):
        if col not in aligned.columns:
            aligned[col] = np.nan
    return aligned


class Executor:
    """Drives backtests for a batch of candidates and emits summary + sensitivity.

    Parameters
    ----------
    generator_registry
        Mapping from family name -> generator instance with a
        ``generate(params: dict) -> type | object`` method.
    features_builder
        Optional callable that turns ``(candidate, data_bundle)`` into the
        OHLC feature frame consumed by ``simulate``. When omitted, the
        executor expects ``data_bundle["market_data"]`` to be the OHLC frame
        and feeds it through the candidate's ``compute_signals``.
    base_params
        Baseline ``ExecParams`` for the primary run; sensitivity variants
        are derived by replacing fields on this object.
    """

    def __init__(
        self,
        generator_registry: dict[str, Any],
        features_builder: FeaturesBuilder | None = None,
        base_params: ExecParams | None = None,
    ) -> None:
        self._registry = dict(generator_registry)
        self._features_builder = features_builder
        self._base_params = base_params or ExecParams()

    def run_candidate(
        self,
        candidate: Candidate,
        data: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        """Execute one candidate and return ``{trades_df, summary, sensitivity, robustness}``."""
        strategy = _resolve_strategy(candidate, self._registry)

        if self._features_builder is not None:
            features = self._features_builder(candidate, data)
        else:
            market = data.get("market_data")
            if market is None:
                raise KeyError("data bundle missing 'market_data' frame")
            signals = strategy.compute_signals(market)
            features = _signals_to_features(signals, market)

        if features.empty:
            empty = pd.DataFrame()
            return {
                "candidate_id": candidate.candidate_id,
                "trades_df": empty,
                "summary": _summarize(empty),
                "sensitivity": pd.DataFrame(),
                "robustness": "LOW",
            }

        trades = simulate(features, self._base_params)
        grid = _sensitivity_grid(features, self._base_params)
        return {
            "candidate_id": candidate.candidate_id,
            "trades_df": trades,
            "summary": _summarize(trades),
            "sensitivity": grid,
            "robustness": _classify_robustness(grid),
        }

    def execute(
        self,
        candidates: list[Candidate],
        data: dict[str, pd.DataFrame],
    ) -> dict[str, dict[str, Any]]:
        """Run all candidates, returning ``{candidate_id: result_dict}``."""
        return {c.candidate_id: self.run_candidate(c, data) for c in candidates}
