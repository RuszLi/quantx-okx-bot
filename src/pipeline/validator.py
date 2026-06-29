"""Validator — IS gate, CPCV, WFA, DSR, PBO evaluation.

Phase 4 implementation. Aligns with `docs/plans/2026-06-28-1000-*.md` §Phase 1.2
and `src/pipeline/protocol.py` constants. R-based equity (Decision D4).

References
----------
- López de Prado, *Advances in Financial Machine Learning* — CPCV, embargo, PBO.
- Bailey & López de Prado (2014), *The Deflated Sharpe Ratio*.
"""

from __future__ import annotations

from itertools import combinations
from statistics import NormalDist
from typing import Any, Literal

import numpy as np
import pandas as pd

from .protocol import (
    CPCV_PARAMS,
    DSR_P_VALUE_MAX,
    IS_GATE,
    PBO_FRACTION_POSITIVE_MIN,
    PBO_MAX,
    REPARAM_GATE,
)

Verdict = Literal["PASS", "REPARAM", "ABORT"]

_STANDARD_NORMAL = NormalDist()


def _safe_sharpe(returns: np.ndarray, eps: float = 1e-12) -> float:
    if returns.size == 0:
        return 0.0
    sd = float(np.std(returns, ddof=1)) if returns.size > 1 else 0.0
    if sd < eps:
        return 0.0
    return float(np.mean(returns) / sd)


def is_gate(trades_df: pd.DataFrame, summary: dict[str, Any]) -> dict[str, Any]:
    """Quick filter — Plan §Phase 1.2 IS gate.

    Returns ``{verdict, reasons}``.
      - ABORT if any hard fail (n_trades<10, avg_holding_bars==0, or any IS
        threshold breached by >50%).
      - REPARAM if metrics meet ``REPARAM_GATE`` but miss IS_GATE.
      - PASS if all IS_GATE thresholds met.
    """
    reasons: list[str] = []

    n_trades = int(summary.get("n_trades", 0))
    avg_hold = float(summary.get("avg_holding_bars", 0.0))
    wr = float(summary.get("win_rate", 0.0))
    ev = float(summary.get("ev_R", 0.0))
    pf = float(summary.get("profit_factor", 0.0))
    mcl = int(summary.get("max_consec_losses", 0))

    if n_trades < 10:
        reasons.append(f"n_trades={n_trades} < 10 (insufficient sample)")
        return {"verdict": "ABORT", "reasons": reasons}
    if avg_hold <= 0:
        reasons.append("avg_holding_bars=0 (weekend_wick_rrmin-style false positive)")
        return {"verdict": "ABORT", "reasons": reasons}

    wr_ok = wr >= IS_GATE["win_rate_min"]
    ev_ok = ev >= IS_GATE["ev_R_min"]
    pf_ok = pf >= IS_GATE["profit_factor_min"]
    mcl_ok = mcl <= IS_GATE["max_consec_losses_max"]

    if wr_ok and ev_ok and pf_ok and mcl_ok:
        return {"verdict": "PASS", "reasons": ["IS gate met"]}

    if not wr_ok:
        reasons.append(f"win_rate={wr:.4f} < {IS_GATE['win_rate_min']}")
    if not ev_ok:
        reasons.append(f"ev_R={ev:.4f} < {IS_GATE['ev_R_min']}")
    if not pf_ok:
        reasons.append(f"profit_factor={pf:.4f} < {IS_GATE['profit_factor_min']}")
    if not mcl_ok:
        reasons.append(f"max_consec_losses={mcl} > {IS_GATE['max_consec_losses_max']}")

    if wr >= REPARAM_GATE["win_rate_min"] and ev >= REPARAM_GATE["ev_R_min"]:
        return {"verdict": "REPARAM", "reasons": reasons}
    return {"verdict": "ABORT", "reasons": reasons}


def _purged_groups(
    n: int,
    n_groups: int,
    test_group_ids: tuple[int, ...],
    embargo_pct: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (train_idx, test_idx) for a CPCV split with purge + embargo."""
    edges = np.linspace(0, n, n_groups + 1, dtype=int)
    test_mask = np.zeros(n, dtype=bool)
    for g in test_group_ids:
        test_mask[edges[g]:edges[g + 1]] = True

    embargo = max(1, int(np.ceil(n * embargo_pct)))
    purge_mask = test_mask.copy()
    for i in np.where(test_mask)[0]:
        lo = max(0, i - embargo)
        hi = min(n, i + embargo + 1)
        purge_mask[lo:hi] = True

    train_idx = np.where(~purge_mask)[0]
    test_idx = np.where(test_mask)[0]
    return train_idx, test_idx


def cpcv_score(
    returns: pd.Series | np.ndarray,
    n_groups: int = CPCV_PARAMS["n_groups"],
    n_test_groups: int = CPCV_PARAMS["n_test_groups"],
    embargo_pct: float = CPCV_PARAMS["embargo_pct"],
) -> dict[str, float]:
    """Combinatorial Purged Cross-Validation with PBO estimation.

    The series is split into ``n_groups`` chronological groups; for every
    combination of ``n_test_groups`` test groups (with neighbour purge +
    embargo), we compute a test Sharpe. PBO ≡ fraction of combinations whose
    test Sharpe falls in the bottom half of all test Sharpes. The
    ``fraction_positive`` is the share of combinations with positive test
    Sharpe — Plan §Phase 1.2 thresholds it at 0.65.
    """
    arr = np.asarray(returns, dtype=float)
    n = arr.size
    if n < n_groups * 2:
        return {"pbo": 1.0, "fraction_positive": 0.0, "median_sharpe": 0.0, "n_splits": 0}

    sharpes: list[float] = []
    for combo in combinations(range(n_groups), n_test_groups):
        _, test_idx = _purged_groups(n, n_groups, combo, embargo_pct)
        if test_idx.size < 2:
            continue
        sharpes.append(_safe_sharpe(arr[test_idx]))

    if not sharpes:
        return {"pbo": 1.0, "fraction_positive": 0.0, "median_sharpe": 0.0, "n_splits": 0}

    sharpes_arr = np.asarray(sharpes)
    median = float(np.median(sharpes_arr))
    pbo = float((sharpes_arr < median).mean())
    fraction_positive = float((sharpes_arr > 0).mean())
    return {
        "pbo": pbo,
        "fraction_positive": fraction_positive,
        "median_sharpe": median,
        "n_splits": len(sharpes),
    }


def wfa_score(
    returns: pd.Series | np.ndarray,
    train_size: int,
    test_size: int,
    n_splits: int = 5,
) -> dict[str, float]:
    """Rolling walk-forward analysis (enhancement-only, non-blocking).

    Returns ``{oos_sharpe, fraction_positive, n_splits}``.
    """
    arr = np.asarray(returns, dtype=float)
    n = arr.size
    step = max(1, (n - train_size - test_size) // max(1, n_splits - 1)) if n_splits > 1 else 0
    sharpes: list[float] = []
    start = 0
    for _ in range(n_splits):
        train_end = start + train_size
        test_end = train_end + test_size
        if test_end > n:
            break
        sharpes.append(_safe_sharpe(arr[train_end:test_end]))
        start += step
    if not sharpes:
        return {"oos_sharpe": 0.0, "fraction_positive": 0.0, "n_splits": 0}
    return {
        "oos_sharpe": float(np.mean(sharpes)),
        "fraction_positive": float((np.asarray(sharpes) > 0).mean()),
        "n_splits": len(sharpes),
    }


def dsr_score(
    sharpe_estimates: pd.Series | np.ndarray,
    n_trials: int,
    returns: pd.Series | np.ndarray,
) -> dict[str, float]:
    """Bailey & López de Prado (2014) Deflated Sharpe Ratio p-value.

    ``sharpe_estimates`` is the cross-trial Sharpe distribution (e.g. CPCV
    test Sharpes). ``returns`` is the in-sample per-trade R series of the
    candidate under test. Returns ``{p_value, deflated_sharpe, sr_threshold}``.
    """
    sr_dist = np.asarray(sharpe_estimates, dtype=float)
    r = np.asarray(returns, dtype=float)
    n = r.size
    if n < 4 or sr_dist.size < 2 or n_trials < 2:
        return {"p_value": 1.0, "deflated_sharpe": 0.0, "sr_threshold": 0.0}

    sr_hat = _safe_sharpe(r)
    sr_std = float(np.std(sr_dist, ddof=1)) if sr_dist.size > 1 else 0.0
    if sr_std <= 0:
        return {"p_value": 1.0, "deflated_sharpe": 0.0, "sr_threshold": 0.0}

    # Expected maximum Sharpe across n_trials i.i.d. trials (López de Prado).
    euler_mascheroni = 0.5772156649
    z_high = _STANDARD_NORMAL.inv_cdf(1.0 - 1.0 / n_trials)
    z_low = _STANDARD_NORMAL.inv_cdf(1.0 - 1.0 / (n_trials * np.e))
    sr_threshold = sr_std * ((1.0 - euler_mascheroni) * z_high + euler_mascheroni * z_low)

    # Skew/kurtosis-adjusted DSR — assume normal-ish (skew=0, kurt=3) when sample is small.
    skew = 0.0
    kurt = 3.0
    if n >= 8:
        mu = float(np.mean(r))
        sd = float(np.std(r, ddof=1))
        if sd > 0:
            zr = (r - mu) / sd
            skew = float(np.mean(zr ** 3))
            kurt = float(np.mean(zr ** 4))
    denom = max(1e-9, 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * sr_hat ** 2)
    dsr = float((sr_hat - sr_threshold) * np.sqrt(n - 1) / np.sqrt(denom))
    p_value = float(1.0 - _STANDARD_NORMAL.cdf(dsr))
    return {"p_value": p_value, "deflated_sharpe": dsr, "sr_threshold": sr_threshold}


def evaluate(
    candidate: Any,
    trades_df: pd.DataFrame,
    summary: dict[str, Any],
    robustness: str,
    holdout_returns: pd.Series | np.ndarray | None = None,
) -> dict[str, Any]:
    """Orchestrate IS → CPCV → DSR → robustness → holdout.

    Returns ``{verdict, gate_results, reasons}`` where ``verdict`` is the
    final promotion decision used by ``promoter`` / ``graveyard``.
    """
    reasons: list[str] = []
    gate_results: dict[str, Any] = {}

    is_result = is_gate(trades_df, summary)
    gate_results["is_gate"] = is_result
    if is_result["verdict"] == "ABORT":
        return {"verdict": "ABORT", "gate_results": gate_results, "reasons": is_result["reasons"]}

    pnl = trades_df["pnl_R"].astype(float).values if not trades_df.empty else np.array([])
    cpcv = cpcv_score(pnl)
    gate_results["cpcv"] = cpcv
    if cpcv["pbo"] > PBO_MAX:
        reasons.append(f"CPCV pbo={cpcv['pbo']:.3f} > {PBO_MAX}")
    if cpcv["fraction_positive"] < PBO_FRACTION_POSITIVE_MIN:
        reasons.append(
            f"CPCV fraction_positive={cpcv['fraction_positive']:.3f} < {PBO_FRACTION_POSITIVE_MIN}"
        )

    cpcv_sharpes = np.asarray([cpcv["median_sharpe"]])  # fallback when only median available
    dsr = dsr_score(cpcv_sharpes, n_trials=max(2, cpcv["n_splits"]), returns=pnl)
    gate_results["dsr"] = dsr
    if dsr["p_value"] > DSR_P_VALUE_MAX:
        reasons.append(f"DSR p_value={dsr['p_value']:.4f} > {DSR_P_VALUE_MAX}")

    gate_results["robustness"] = robustness
    if robustness == "LOW":
        reasons.append(f"robustness={robustness} (need MEDIUM or HIGH)")

    if holdout_returns is not None:
        holdout_arr = np.asarray(holdout_returns, dtype=float)
        holdout_ev = float(holdout_arr.mean()) if holdout_arr.size else 0.0
        gate_results["holdout"] = {"ev_R": holdout_ev, "n": int(holdout_arr.size)}
        if holdout_ev <= 0:
            reasons.append(f"holdout ev_R={holdout_ev:.4f} <= 0")

    wfa = wfa_score(pnl, train_size=max(20, len(pnl) // 2), test_size=max(10, len(pnl) // 4))
    gate_results["wfa"] = wfa  # non-blocking per D1

    verdict: Verdict
    if reasons:
        verdict = "REPARAM" if is_result["verdict"] == "PASS" else "ABORT"
    else:
        verdict = "PASS"

    return {"verdict": verdict, "gate_results": gate_results, "reasons": reasons or ["all gates passed"]}


class Validator:
    """Thin OO wrapper preserved for backward compatibility with the stub API."""

    def evaluate(
        self,
        trades_df: pd.DataFrame,
        summary: dict[str, Any],
        robustness: str = "MEDIUM",
        holdout_returns: pd.Series | np.ndarray | None = None,
    ) -> tuple[Verdict, dict[str, Any]]:
        result = evaluate(None, trades_df, summary, robustness, holdout_returns)
        return result["verdict"], result
