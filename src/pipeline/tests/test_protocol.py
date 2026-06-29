"""Protocol-constant tests — verify all constants match the plan."""

import pytest

from src.pipeline.protocol import (
    CPCV_PARAMS,
    DSR_P_VALUE_MAX,
    HOLDOUT_WINDOW_START,
    IS_GATE,
    PBO_FRACTION_POSITIVE_MIN,
    PBO_MAX,
    REPARAM_GATE,
    TRAIN_WINDOW_END,
    TRAIN_WINDOW_START,
)


class TestISGate:
    def test_thresholds(self):
        assert IS_GATE["win_rate_min"] == 0.45
        assert IS_GATE["ev_R_min"] == 0.15
        assert IS_GATE["profit_factor_min"] == 1.3
        assert IS_GATE["max_consec_losses_max"] == 6


class TestReparamGate:
    def test_thresholds(self):
        assert REPARAM_GATE["win_rate_min"] == 0.40
        assert REPARAM_GATE["ev_R_min"] == 0.05


class TestCPCV:
    def test_params(self):
        assert CPCV_PARAMS["n_groups"] == 8
        assert CPCV_PARAMS["n_test_groups"] == 2
        assert CPCV_PARAMS["embargo_pct"] == 0.01
        assert CPCV_PARAMS["label_horizon"] == 5


class TestPBO:
    def test_thresholds(self):
        assert PBO_MAX == 0.40
        assert PBO_FRACTION_POSITIVE_MIN == 0.65


class TestDSR:
    def test_thresholds(self):
        assert DSR_P_VALUE_MAX == 0.05


class TestWindows:
    def test_boundaries(self):
        assert TRAIN_WINDOW_START == "2024-01-01"
        assert TRAIN_WINDOW_END == "2025-01-01"
        assert HOLDOUT_WINDOW_START == "2025-01-01"
