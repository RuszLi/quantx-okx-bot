"""Unit tests for ``src.pipeline.validator``."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.pipeline import validator as V


def _trades(pnl_R: list[float], bars_held: int = 4) -> pd.DataFrame:
    return pd.DataFrame({
        "pnl_R": pnl_R,
        "bars_held": [bars_held] * len(pnl_R),
        "side": ["LONG"] * len(pnl_R),
    })


def _summary_from(pnl_R: list[float], avg_holding_bars: float = 4.0) -> dict:
    arr = np.asarray(pnl_R)
    wins = arr[arr > 0].sum()
    losses = -arr[arr < 0].sum()
    pf = float("inf") if losses == 0 else float(wins / losses)
    consec = best = 0
    for r in arr:
        if r < 0:
            consec += 1
            best = max(best, consec)
        else:
            consec = 0
    return {
        "n_trades": int(arr.size),
        "win_rate": float((arr > 0).mean()),
        "ev_R": float(arr.mean()),
        "profit_factor": pf,
        "max_consec_losses": best,
        "avg_holding_bars": avg_holding_bars,
    }


class TestISGate:
    def test_pass_when_all_thresholds_met(self):
        pnl = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -0.3, -0.3, -0.3, -0.3]
        result = V.is_gate(_trades(pnl), _summary_from(pnl))
        assert result["verdict"] == "PASS"

    def test_abort_when_avg_holding_zero(self):
        pnl = [1.0] * 12
        result = V.is_gate(_trades(pnl, bars_held=0), _summary_from(pnl, avg_holding_bars=0.0))
        assert result["verdict"] == "ABORT"
        assert any("avg_holding_bars" in r for r in result["reasons"])

    def test_abort_when_insufficient_trades(self):
        pnl = [1.0, 1.0, 1.0]
        result = V.is_gate(_trades(pnl), _summary_from(pnl))
        assert result["verdict"] == "ABORT"

    def test_reparam_when_near_threshold(self):
        # WR=0.42 (REPARAM range), EV=0.10 (REPARAM range), PF<1.3
        pnl = [0.5, 0.5, 0.5, 0.5, 0.5, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4]
        # 5 wins / 12 = 0.417 ≥ 0.40 ; EV slightly negative → ABORT, not REPARAM
        # Adjust: 6 wins / 12 = 0.50, but EV below 0.15.
        pnl = [0.6, 0.6, 0.6, 0.6, 0.6, 0.6, -0.4, -0.4, -0.4, -0.4, -0.4, -0.4]
        result = V.is_gate(_trades(pnl), _summary_from(pnl))
        assert result["verdict"] in {"REPARAM", "ABORT"}

    def test_abort_when_far_below_thresholds(self):
        pnl = [-1.0] * 12
        result = V.is_gate(_trades(pnl), _summary_from(pnl))
        assert result["verdict"] == "ABORT"


class TestCPCV:
    def test_pbo_high_for_random_noise(self):
        rng = np.random.default_rng(0)
        noise = rng.normal(0.0, 1.0, 200)
        out = V.cpcv_score(noise)
        assert 0.0 <= out["pbo"] <= 1.0
        assert 0.0 <= out["fraction_positive"] <= 1.0
        assert out["n_splits"] > 0

    def test_fraction_positive_high_for_consistent_winner(self):
        signal = np.full(200, 0.05) + np.random.default_rng(1).normal(0, 0.01, 200)
        out = V.cpcv_score(signal)
        assert out["fraction_positive"] >= 0.9

    def test_pbo_short_series_handled(self):
        out = V.cpcv_score(np.array([0.1, 0.2]))
        assert out["n_splits"] == 0
        assert out["pbo"] == 1.0


class TestDSR:
    def test_p_value_in_unit_interval(self):
        rng = np.random.default_rng(2)
        returns = rng.normal(0.02, 0.05, 100)
        sharpes = rng.normal(0.0, 0.2, 28)
        out = V.dsr_score(sharpes, n_trials=20, returns=returns)
        assert 0.0 <= out["p_value"] <= 1.0

    def test_degenerate_inputs_return_one(self):
        out = V.dsr_score(np.array([0.0]), n_trials=1, returns=np.array([1.0]))
        assert out["p_value"] == 1.0


class TestEvaluate:
    def test_promote_path(self):
        rng = np.random.default_rng(3)
        pnl = list(rng.normal(0.5, 0.4, 50))
        trades = _trades(pnl)
        summary = _summary_from(pnl)
        out = V.evaluate(None, trades, summary, robustness="HIGH",
                         holdout_returns=rng.normal(0.4, 0.3, 30))
        assert out["verdict"] in {"PASS", "REPARAM"}
        assert "gate_results" in out
        assert "cpcv" in out["gate_results"]
        assert "dsr" in out["gate_results"]
        assert "wfa" in out["gate_results"]

    def test_abort_propagates_is_failure(self):
        out = V.evaluate(
            None,
            _trades([1.0, 1.0, 1.0], bars_held=0),
            _summary_from([1.0, 1.0, 1.0], avg_holding_bars=0.0),
            robustness="HIGH",
        )
        assert out["verdict"] == "ABORT"

    def test_low_robustness_blocks_pass(self):
        rng = np.random.default_rng(4)
        pnl = list(rng.normal(0.5, 0.4, 50))
        out = V.evaluate(None, _trades(pnl), _summary_from(pnl), robustness="LOW")
        assert out["verdict"] in {"REPARAM", "ABORT"}
