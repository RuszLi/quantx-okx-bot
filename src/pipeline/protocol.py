"""Validation protocol constants for the V3.2 automated edge discovery pipeline.

All constants are sourced from:
    docs/plans/2026-06-28-1000-strategy-v3.2-automated-edge-discovery-pipeline.md
    §Phase 1.2 (Validation Protocol Parameters) and Decision Log D1.

This module contains ONLY constants — no validation logic, no business rules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# §Phase 1.2 — IS Gate (initial filter before CPCV)
# ---------------------------------------------------------------------------

IS_GATE: dict[str, float | int] = {
    "win_rate_min": 0.45,
    "ev_R_min": 0.15,
    "profit_factor_min": 1.3,
    "max_consec_losses_max": 6,
}

# ---------------------------------------------------------------------------
# §Phase 1.2 — Reparameterization Gate (post-CPCV, before DSR)
# ---------------------------------------------------------------------------

REPARAM_GATE: dict[str, float] = {
    "win_rate_min": 0.40,
    "ev_R_min": 0.05,
}

# ---------------------------------------------------------------------------
# §Phase 1.2 — CPCV (Combinatorial Purged Cross-Validation) parameters
# ---------------------------------------------------------------------------

CPCV_PARAMS: dict[str, float | int] = {
    "n_groups": 8,
    "n_test_groups": 2,
    "embargo_pct": 0.01,
    "label_horizon": 5,
}

# ---------------------------------------------------------------------------
# §Phase 1.2 — PBO (Probability of Backtest Overfitting) thresholds
# ---------------------------------------------------------------------------

PBO_MAX: float = 0.40
PBO_FRACTION_POSITIVE_MIN: float = 0.65

# ---------------------------------------------------------------------------
# §Phase 1.2 — DSR (Deflated Sharpe Ratio) significance threshold
# ---------------------------------------------------------------------------

DSR_P_VALUE_MAX: float = 0.05

# ---------------------------------------------------------------------------
# §Phase 1.2 — Data window boundaries
# ---------------------------------------------------------------------------

TRAIN_WINDOW_START: str = "2024-01-01"
TRAIN_WINDOW_END: str = "2025-01-01"  # exclusive end of training data
HOLDOUT_WINDOW_START: str = "2025-01-01"  # inclusive, fixed — not overridable by CLI
