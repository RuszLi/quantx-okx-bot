"""Live Echo Runner SL/TP 方向校验单元测试."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _import_live_module():
    import sys

    sys.path.insert(0, str(ROOT))
    import scripts.run_live_echo as live

    return live


@pytest.fixture
def live():
    return _import_live_module()


def test_attach_sltp_long_ok(live):
    with patch.object(live, "trade_api") as mock_trade:
        mock_api = MagicMock()
        mock_api.place_algo_order.return_value = {"code": "0", "data": [{"algoId": "123"}]}
        mock_trade.return_value = mock_api

        ok = live.attach_sltp_via_algo_order("SOL-USDT-SWAP", "buy", "long", 1, 100.0, 99.0, 101.0)
        assert ok is True

        kwargs = mock_api.place_algo_order.call_args.kwargs
        assert kwargs["side"] == "sell"
        assert kwargs["posSide"] == "long"
        assert kwargs["reduceOnly"] is True
        assert float(kwargs["slTriggerPx"]) == 99.0
        assert float(kwargs["tpTriggerPx"]) == 101.0


def test_attach_sltp_short_ok(live):
    with patch.object(live, "trade_api") as mock_trade:
        mock_api = MagicMock()
        mock_api.place_algo_order.return_value = {"code": "0", "data": [{"algoId": "456"}]}
        mock_trade.return_value = mock_api

        ok = live.attach_sltp_via_algo_order("SOL-USDT-SWAP", "sell", "short", 1, 100.0, 101.0, 99.0)
        assert ok is True

        kwargs = mock_api.place_algo_order.call_args.kwargs
        assert kwargs["side"] == "buy"
        assert kwargs["posSide"] == "short"
        assert kwargs["reduceOnly"] is True
        assert float(kwargs["slTriggerPx"]) == 101.0
        assert float(kwargs["tpTriggerPx"]) == 99.0


def test_attach_sltp_direction_mismatch_is_rejected(live):
    with patch.object(live, "trade_api") as mock_trade:
        mock_api = MagicMock()
        mock_trade.return_value = mock_api

        # 做多但 stop > fill，应被拦截且不调用 place_algo_order
        ok = live.attach_sltp_via_algo_order("SOL-USDT-SWAP", "buy", "long", 1, 100.0, 101.0, 99.0)
        assert ok is False
        mock_api.place_algo_order.assert_not_called()


def test_place_market_close_forces_reduce_only(live):
    with patch.object(live, "trade_api") as mock_trade:
        mock_api = MagicMock()
        mock_api.place_order.return_value = {"code": "0", "data": [{"ordId": "789"}]}
        mock_trade.return_value = mock_api

        ok = live.place_market_close("SOL-USDT-SWAP", "sell", 1, "long")
        assert ok is True

        kwargs = mock_api.place_order.call_args.kwargs
        assert kwargs["reduceOnly"] is True


def test_live_strategy_edges_excludes_weekend_wick_on_weekdays(live):
    friday = datetime(2026, 6, 26, 12, tzinfo=timezone.utc)

    edges = live.live_strategy_edges(friday)

    assert edges == {"C"}


def test_live_strategy_edges_enables_weekend_wick_on_weekends(live):
    saturday = datetime(2026, 6, 27, 12, tzinfo=timezone.utc)

    edges = live.live_strategy_edges(saturday)

    assert edges == {"C", "D"}


def test_run_once_passes_live_strategy_edges_to_pipeline(live, monkeypatch):
    calls = []
    monkeypatch.setattr(live, "get_equity", lambda: 3.5)
    monkeypatch.setattr(live, "live_strategy_edges", lambda: {"C"})

    def fake_compute_ensemble_signals(**kwargs):
        calls.append(kwargs)
        import pandas as pd

        return pd.DataFrame()

    monkeypatch.setattr(live, "compute_ensemble_signals", fake_compute_ensemble_signals)

    risk_guard = MagicMock()
    risk_guard.is_halted = False

    live.run_once({}, risk_guard)

    assert calls == [{"equity": 3.5, "risk_guard": risk_guard, "strategy_edges": {"C"}}]
