from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from scripts.run_v3_phase0_backtest import (
    StrategyRunConfig,
    run_strategy_on_universe,
)
from src.backtest.strategies.listing_fade import ListingFadeStrategy
from src.backtest.strategies.weekend_wick import WeekendWickStrategy


def _make_1m_klines(*, periods: int = 6 * 60) -> pd.DataFrame:
    """构造一段周六 1m kline，供 orchestrator 频率对齐测试复用。"""
    idx = pd.date_range("2026-06-27 00:00:00", periods=periods, freq="1min", tz="UTC")
    df = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 10_000_000.0,
            "quote_volume": 1_000_000_000.0,
        },
        index=idx,
    )
    # 保留一个明显 spike，避免后续若不打桩也能肉眼看出这是小时级场景。
    spike_start = pd.Timestamp("2026-06-27 02:00:00", tz="UTC")
    spike_end = pd.Timestamp("2026-06-27 02:59:00", tz="UTC")
    mask = (df.index >= spike_start) & (df.index <= spike_end)
    df.loc[mask, "high"] = 120.0
    df.loc[mask, "close"] = 118.0
    return df


def _make_dummy_signal(entry_ts: str) -> pd.DataFrame:
    ts = pd.Timestamp(entry_ts, tz="UTC")
    return pd.DataFrame(
        [
            {
                "entry_ts": ts,
                "signal": -1,
                "entry_price": 118.0,
                "target_price": 100.0,
                "stop_price": 121.0,
            }
        ]
    )


def test_weekend_wick_exit_simulation_uses_hourly_klines() -> None:
    """weekend_wick 配置 bar_freq='1h'，exit 模拟必须收到 1h klines，而非 1m。

    这是 V3 backtest 与实盘脱节的根因之一：原代码总是把 1m kline 传给
    simulate_exits，导致 time_stop_bars=2 实际只持仓 2 分钟，而非 2 小时。
    """
    klines_1m = _make_1m_klines()
    cfg = StrategyRunConfig(
        name="weekend_wick",
        edge="D",
        is_event_driven=False,
        time_stop_bars=2,
        risk_per_trade_R=0.15,
        universe=["TESTUSDT"],
    )

    captured_calls: list[dict[str, object]] = []

    def _capture_simulate_exits(**kwargs: object) -> pd.DataFrame:
        captured_calls.append(kwargs)
        # 返回空 trades，避免下游汇总逻辑干扰本测试的关注点
        return pd.DataFrame()

    with (
        patch(
            "scripts.run_v3_phase0_backtest.load_universe_data",
            return_value={"klines": klines_1m},
        ),
        patch.object(
            WeekendWickStrategy,
            "compute_signals",
            return_value=_make_dummy_signal("2026-06-27 02:00:00"),
        ),
        patch(
            "scripts.run_v3_phase0_backtest.simulate_exits",
            side_effect=_capture_simulate_exits,
        ),
    ):
        run_strategy_on_universe(cfg, btc_klines=pd.DataFrame())

    assert captured_calls, "simulate_exits 应该被调用至少一次"
    klines_passed = captured_calls[0]["klines"]
    median_delta = klines_passed.index.to_series().diff().median()

    assert median_delta >= pd.Timedelta(minutes=30), (
        f"weekend_wick 的 exit klines 应该是 1h 频率，"
        f"但实际传入的 klines 中位数间隔为 {median_delta}"
    )


def test_event_driven_listing_fade_keeps_minute_klines() -> None:
    """event-driven 的 listing_fade 仍应使用 1m kline 做 exit 模拟，不受 bar_freq 影响."""
    klines_1m = _make_1m_klines(periods=30)

    cfg = StrategyRunConfig(
        name="listing_fade",
        edge="A",
        is_event_driven=True,
        time_stop_bars=5,
        risk_per_trade_R=0.30,
        universe=["TESTUSDT"],
    )

    captured_calls: list[dict[str, object]] = []

    def _capture_simulate_exits(**kwargs: object) -> pd.DataFrame:
        captured_calls.append(kwargs)
        return pd.DataFrame()

    with (
        patch(
            "scripts.run_v3_phase0_backtest.load_universe_data",
            return_value={"klines": klines_1m},
        ),
        patch.object(
            ListingFadeStrategy,
            "compute_signals",
            return_value=_make_dummy_signal("2026-06-27 00:05:00"),
        ),
        patch(
            "scripts.run_v3_phase0_backtest.simulate_exits",
            side_effect=_capture_simulate_exits,
        ),
    ):
        run_strategy_on_universe(cfg, btc_klines=pd.DataFrame())

    assert captured_calls, "simulate_exits 应该被调用至少一次"
    klines_passed = captured_calls[0]["klines"]
    median_delta = klines_passed.index.to_series().diff().median()

    assert median_delta <= pd.Timedelta(minutes=2), (
        f"listing_fade 是 event-driven，应继续使用 1m klines，"
        f"但实际传入的 klines 中位数间隔为 {median_delta}"
    )
