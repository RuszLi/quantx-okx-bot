"""Unit tests for ``src.pipeline.executor``."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import ExecParams
from src.pipeline.candidate import Candidate
from src.pipeline.executor import Executor, _signals_to_features


class _ConstSignalStrategy:
    """Toy strategy emitting a single LONG signal at a known bar."""

    def __init__(self, entry_idx: int = 5, direction: int = 1, tp_pct: float = 0.04, sl_pct: float = 0.012):
        self.entry_idx = entry_idx
        self.direction = direction
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct

    def compute_signals(self, market_data: pd.DataFrame, external_events=None) -> pd.DataFrame:
        if len(market_data) <= self.entry_idx:
            return pd.DataFrame()
        ts = market_data.index[self.entry_idx]
        entry = float(market_data.iloc[self.entry_idx]["close"])
        target = entry * (1.0 + self.direction * self.tp_pct)
        stop = entry * (1.0 - self.direction * self.sl_pct)
        return pd.DataFrame([{
            "entry_ts": ts,
            "signal": self.direction,
            "entry_price": entry,
            "target_price": target,
            "stop_price": stop,
        }])


class _ConstGenerator:
    """Generator returning a fixed strategy instance regardless of params."""

    def __init__(self, strategy_instance):
        self._instance = strategy_instance

    def generate(self, params):
        return self._instance


@pytest.fixture
def synthetic_market() -> pd.DataFrame:
    idx = pd.date_range("2024-06-01", periods=60, freq="1h", tz="UTC")
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0.1, 0.5, len(idx)))
    return pd.DataFrame({
        "open": base, "close": base + 0.05, "high": base + 0.6, "low": base - 0.6,
        "volume": 1000.0,
    }, index=idx)


def test_signals_to_features_aligns_grid(synthetic_market):
    strat = _ConstSignalStrategy(entry_idx=3)
    signals = strat.compute_signals(synthetic_market)
    features = _signals_to_features(signals, synthetic_market)
    assert "signal" in features.columns and "entry_price" in features.columns
    nonzero = features[features["signal"] != 0]
    assert len(nonzero) == 1
    assert nonzero.index[0] == synthetic_market.index[3]


def test_run_candidate_returns_summary_and_grid(synthetic_market):
    strat_inst = _ConstSignalStrategy(entry_idx=4)
    registry = {"toy": _ConstGenerator(strat_inst)}
    executor = Executor(registry, base_params=ExecParams(time_stop_bars=2))
    cand = Candidate(candidate_id="toy_x", family="toy", params={})
    result = executor.run_candidate(cand, {"market_data": synthetic_market})
    summary = result["summary"]
    assert set(summary) >= {"n_trades", "win_rate", "ev_R", "profit_factor",
                            "max_consec_losses", "avg_holding_bars"}
    grid = result["sensitivity"]
    assert len(grid) == 27
    assert set(grid["time_stop_bars"]) == {1, 2, 4}
    assert result["robustness"] in {"HIGH", "MEDIUM", "LOW"}


def test_executor_empty_signals_returns_low_robustness(synthetic_market):
    class _NoSig:
        def compute_signals(self, md, _=None):
            return pd.DataFrame()
    registry = {"toy": _ConstGenerator(_NoSig())}
    executor = Executor(registry)
    cand = Candidate(candidate_id="nosig", family="toy", params={})
    result = executor.run_candidate(cand, {"market_data": synthetic_market})
    assert result["summary"]["n_trades"] == 0
    assert result["robustness"] == "LOW"
    assert result["sensitivity"].empty


def test_unknown_family_raises(synthetic_market):
    executor = Executor({})
    with pytest.raises(KeyError):
        executor.run_candidate(
            Candidate(candidate_id="x", family="ghost", params={}),
            {"market_data": synthetic_market},
        )
