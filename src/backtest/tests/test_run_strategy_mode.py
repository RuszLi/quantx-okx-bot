import pandas as pd

from src.backtest import run


def test_run_strategy_mode_dispatches_named_strategy(monkeypatch, tmp_path):
    called = {}

    class FakeStrategy:
        config = type("Cfg", (), {"is_event_driven": False, "universe_fn": staticmethod(lambda _=None: ["BTCUSDT"])})()

        def compute_signals(self, market_data, external_events=None):
            called["market_data_rows"] = len(market_data)
            called["external_events_rows"] = 0 if external_events is None else len(external_events)
            return pd.DataFrame([
                {
                    "event_id": "evt-1",
                    "symbol": "BTC-USDT-SWAP",
                    "entry_ts": pd.Timestamp("2026-06-25T00:00:00Z"),
                    "exit_ts": pd.Timestamp("2026-06-25T00:10:00Z"),
                    "signal": -1,
                    "entry_price": 100.0,
                    "target_price": 95.0,
                    "stop_price": 105.0,
                    "exit_price": 96.0,
                    "exit_reason": "TP",
                    "risk_fraction": 0.2,
                }
            ])

    monkeypatch.setattr(run, "load_strategy", lambda name: FakeStrategy())
    monkeypatch.setattr(run, "cache_raw", lambda symbol, start, end: tmp_path / f"{symbol}.parquet")
    monkeypatch.setattr(pd, "read_parquet", lambda path: pd.DataFrame({"close": [1], "high": [1], "low": [1], "open": [1], "volume": [1], "quote_volume": [1]}, index=pd.DatetimeIndex([pd.Timestamp("2026-06-25T00:00:00Z")], name="ts")))

    out_dir = tmp_path / "reports"
    out_dir.mkdir()
    trades, summary = run.run_named_strategy(
        strategy_name="beta_decouple",
        start=pd.Timestamp("2026-06-25").date(),
        end=pd.Timestamp("2026-06-25").date(),
        universe_path=None,
        out_dir=out_dir,
    )

    assert len(trades) == 1
    assert called["market_data_rows"] == 1
    assert summary["strategy_name"] == "beta_decouple"
