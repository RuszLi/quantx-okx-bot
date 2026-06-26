"""V3 信号管道 — 共享的信号计算与数据获取逻辑.

纸交易与实盘运行器共同引用此模块，避免信号逻辑重复。
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.backtest.strategies.beta_decouple import BetaDecoupleStrategy
from src.backtest.strategies.ensemble import EnsembleStrategy
from src.backtest.strategies.weekend_wick import WeekendWickStrategy
from src.live.risk_guard import RiskGuard
from src.okx_sdk import market_api, public_api

SYMBOL_MAP: dict[str, str] = {
    s.split("USDT")[0] + "-USDT-SWAP": s
    for s in [
        "SOLUSDT", "DOGEUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT",
        "POLUSDT", "ARBUSDT", "OPUSDT", "APTUSDT", "SUIUSDT", "INJUSDT",
        "NEARUSDT", "LDOUSDT", "WIFUSDT", "FETUSDT", "RENDERUSDT", "TIAUSDT",
        "SEIUSDT", "ATOMUSDT", "DOTUSDT", "FILUSDT", "BCHUSDT", "LTCUSDT",
    ]
}

OKX_INST_IDS = list(SYMBOL_MAP.keys())
N_HOURS_HISTORY = 96
_CANDLE_COLS = ["ts", "open", "high", "low", "close", "volume", "quote_volume"]
_RETRY_SLEEP = [1, 3, 5]

_CLIENT = market_api()
_VALIDATED = False


def _okx_req(fn, *args, **kwargs):
    for wait in _RETRY_SLEEP:
        try:
            return fn(*args, **kwargs)
        except Exception:
            time.sleep(wait)
    return fn(*args, **kwargs)


def _rows_to_frame(rows: list[list[str]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(
        rows,
        columns=["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"],
    )
    for c in ["open", "high", "low", "close", "vol", "volCcyQuote"]:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    frame = frame.rename(columns={"vol": "volume", "volCcyQuote": "quote_volume"})
    frame["ts"] = pd.to_datetime(pd.to_numeric(frame["ts"], errors="coerce"), unit="ms", utc=True)
    frame = frame.dropna(subset=["ts", "close"])
    return frame[_CANDLE_COLS].sort_values("ts").reset_index(drop=True)


def fetch_1h_candles(inst_id: str, limit: int = N_HOURS_HISTORY) -> pd.DataFrame:
    result = _okx_req(_CLIENT.get_candlesticks, instId=inst_id, bar="1H", limit=limit)
    if result.get("code") != "0":
        return pd.DataFrame()
    return _rows_to_frame(result.get("data") or [])


def build_c_market_data(kline_1h: pd.DataFrame) -> pd.DataFrame:
    if kline_1h.empty or len(kline_1h) < 5:
        return pd.DataFrame()
    df = kline_1h.set_index("ts")
    frame = pd.DataFrame(index=df.index)
    frame["btc_close"] = df["close"]
    frame["btc_return_60m"] = df["close"].pct_change().fillna(0.0)
    realized_vol = df["close"].pct_change().rolling(60, min_periods=5).std().fillna(0.0)
    frame["btc_rv_pct"] = realized_vol.rank(pct=True).fillna(0.0)
    frame["alt_close"] = df["close"]
    frame["alt_vwap_60m"] = df["close"].rolling(60, min_periods=5).mean().fillna(df["close"])
    frame["alt_volume_24h"] = df["quote_volume"].rolling(24, min_periods=5).sum().fillna(0.0)
    age_days = (pd.Series(frame.index, index=frame.index) - frame.index.min()).dt.total_seconds() / 86400.0
    frame["alt_age_days"] = age_days.clip(lower=0.0)
    return frame


def build_d_market_data(kline_1h: pd.DataFrame) -> pd.DataFrame:
    if kline_1h.empty or len(kline_1h) < 2:
        return pd.DataFrame()
    df = kline_1h.set_index("ts")
    frame = df[["open", "high", "low", "close", "volume"]].copy()
    rolling_mean = frame["close"].rolling(24, min_periods=5).mean().fillna(frame["close"])
    rolling_std = frame["close"].rolling(24, min_periods=5).std(ddof=0).fillna(1.0)
    frame["wick_z"] = ((frame["close"] - rolling_mean) / rolling_std.replace(0, 1.0)).abs()
    return frame


def validate_symbols() -> list[str]:
    global _VALIDATED
    if _VALIDATED:
        return OKX_INST_IDS
    okx_swaps = {i["instId"] for i in _okx_req(public_api().get_instruments, instType="SWAP").get("data", []) if i.get("settleCcy") == "USDT"}
    valid = [i for i in OKX_INST_IDS if i in okx_swaps]
    OKX_INST_IDS.clear()
    OKX_INST_IDS.extend(valid)
    _VALIDATED = True
    return OKX_INST_IDS


def load_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def append_csv(path: Path, new_rows: pd.DataFrame) -> None:
    existing = load_csv(path)
    combined = pd.concat([existing, new_rows], ignore_index=True) if not existing.empty else new_rows
    combined.to_csv(path, index=False)


def compute_ensemble_signals(
    inst_ids: list[str] | None = None,
    equity: float = 7.0,
) -> pd.DataFrame:
    validate_symbols()
    targets = inst_ids or OKX_INST_IDS

    strategy_c = BetaDecoupleStrategy()
    strategy_d = WeekendWickStrategy()
    ensemble = EnsembleStrategy()
    risk_guard = RiskGuard()

    signals_c: list[pd.DataFrame] = []
    signals_d: list[pd.DataFrame] = []

    for inst_id in targets:
        candles = fetch_1h_candles(inst_id, N_HOURS_HISTORY)
        if candles.empty or len(candles) < 24:
            continue

        md_c = build_c_market_data(candles)
        if not md_c.empty and len(md_c) >= 5:
            sigs = strategy_c.compute_signals(md_c)
            if not sigs.empty:
                sigs["symbol"] = SYMBOL_MAP[inst_id]
                sigs["strategy_name"] = "beta_decouple"
                sigs["edge"] = "C"
                signals_c.append(sigs)

        md_d = build_d_market_data(candles)
        if not md_d.empty and len(md_d) >= 2:
            sigs = strategy_d.compute_signals(md_d)
            if not sigs.empty:
                sigs["symbol"] = SYMBOL_MAP[inst_id]
                sigs["strategy_name"] = "weekend_wick"
                sigs["edge"] = "D"
                signals_d.append(sigs)

    all_raw = pd.concat(signals_c + signals_d, ignore_index=True) if (signals_c or signals_d) else pd.DataFrame()
    if all_raw.empty:
        return pd.DataFrame()

    result = ensemble.resolve_conflicts(all_raw, available_equity=equity)
    risk_guard.update_equity(equity)

    if risk_guard.is_halted:
        return pd.DataFrame()

    return result
