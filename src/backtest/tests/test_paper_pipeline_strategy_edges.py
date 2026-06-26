from __future__ import annotations

import pandas as pd

from src.paper import pipeline


class _BetaDecoupleStub:
    called = False

    def compute_signals(self, market_data: pd.DataFrame, external_events: pd.DataFrame | None = None) -> pd.DataFrame:
        _BetaDecoupleStub.called = True
        return pd.DataFrame(
            [
                {
                    "entry_ts": market_data.index[-1],
                    "valid_until_ts": market_data.index[-1] + pd.Timedelta(hours=2),
                    "signal": -1,
                    "entry_price": 12.0,
                    "target_price": 11.0,
                    "stop_price": 13.0,
                    "alt_z": 2.5,
                }
            ]
        )


class _WeekendWickStub:
    called = False

    def compute_signals(self, market_data: pd.DataFrame, external_events: pd.DataFrame | None = None) -> pd.DataFrame:
        _WeekendWickStub.called = True
        return pd.DataFrame(
            [
                {
                    "entry_ts": market_data.index[-2],
                    "valid_until_ts": market_data.index[-1],
                    "signal": 1,
                    "entry_price": 10.0,
                    "target_price": 11.0,
                    "stop_price": 9.0,
                }
            ]
        )


def _candles() -> pd.DataFrame:
    ts = pd.date_range("2026-06-26 00:00:00", periods=96, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [10.0] * len(ts),
            "high": [12.0] * len(ts),
            "low": [9.0] * len(ts),
            "close": [11.0] * len(ts),
            "volume": [6_000_000.0] * len(ts),
            "quote_volume": [20_000_000.0] * len(ts),
        }
    )


def test_compute_ensemble_signals_runs_only_requested_edge(monkeypatch) -> None:
    _BetaDecoupleStub.called = False
    _WeekendWickStub.called = False
    monkeypatch.setattr(pipeline, "validate_symbols", lambda: ["SOL-USDT-SWAP"])
    monkeypatch.setattr(pipeline, "fetch_1h_candles", lambda inst_id, limit: _candles())
    monkeypatch.setattr(pipeline, "_build_btc_rv", lambda: None)
    monkeypatch.setattr(pipeline, "BetaDecoupleStrategy", _BetaDecoupleStub)
    monkeypatch.setattr(pipeline, "WeekendWickStrategy", _WeekendWickStub)

    result = pipeline.compute_ensemble_signals(inst_ids=["SOL-USDT-SWAP"], strategy_edges={"C"})

    assert _BetaDecoupleStub.called is True
    assert _WeekendWickStub.called is False
    assert set(result["edge"]) == {"C"}


def test_compute_ensemble_signals_can_include_weekend_edge(monkeypatch) -> None:
    _BetaDecoupleStub.called = False
    _WeekendWickStub.called = False
    monkeypatch.setattr(pipeline, "validate_symbols", lambda: ["SOL-USDT-SWAP"])
    monkeypatch.setattr(pipeline, "fetch_1h_candles", lambda inst_id, limit: _candles())
    monkeypatch.setattr(pipeline, "_build_btc_rv", lambda: None)
    monkeypatch.setattr(pipeline, "BetaDecoupleStrategy", _BetaDecoupleStub)
    monkeypatch.setattr(pipeline, "WeekendWickStrategy", _WeekendWickStub)

    result = pipeline.compute_ensemble_signals(inst_ids=["SOL-USDT-SWAP"], strategy_edges={"C", "D"})

    assert _BetaDecoupleStub.called is True
    assert _WeekendWickStub.called is True
    assert set(result["edge"]) == {"C", "D"}
