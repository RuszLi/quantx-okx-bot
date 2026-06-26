"""Edge A listing_fade 前向监测器.

持续轮询 OKX instruments API 检测新 SWAP 上币事件，
下载 1m kline，运行 listing_fade 策略信号，持久化证据。
信号只记录不执行（paper 模式），为未来实盘积累统计样本。

用法:
    python scripts/run_listing_fade_forward_monitor.py --once
    python scripts/run_listing_fade_forward_monitor.py
    python scripts/run_listing_fade_forward_monitor.py --interval 10
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.backtest.strategies.listing_fade import ListingFadeStrategy
from src.data.okx_klines import download_and_cache
from src.okx_sdk import public_api

# ---------------- 配置 ----------------
MONITOR_ROOT = ROOT / "data" / "listing_fade_monitor"
PROCESSED_PATH = MONITOR_ROOT / "processed_events.json"
EVIDENCE_DIR = MONITOR_ROOT / "evidence"
TRADES_PATH = MONITOR_ROOT / "trades.csv"
LOG_PATH = MONITOR_ROOT / "monitor.log"

MONITOR_ROOT.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------- 日志 ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(str(LOG_PATH), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("listing_fade_monitor")


# ---------------- 工具函数 ----------------
def load_processed() -> dict[str, dict[str, str]]:
    if PROCESSED_PATH.exists():
        return json.loads(PROCESSED_PATH.read_text(encoding="utf-8"))
    return {}


def save_processed(processed: dict[str, dict[str, str]]) -> None:
    PROCESSED_PATH.write_text(json.dumps(processed, indent=2, ensure_ascii=False), encoding="utf-8")


def load_existing_trades() -> pd.DataFrame:
    if TRADES_PATH.exists():
        return pd.read_csv(TRADES_PATH)
    return pd.DataFrame()


def append_trades(new_trades: pd.DataFrame) -> None:
    existing = load_existing_trades()
    combined = pd.concat([existing, new_trades], ignore_index=True) if not existing.empty else new_trades
    combined.to_csv(TRADES_PATH, index=False)
    logger.info(f"  trades.csv 追加完成,总行数={len(combined)}")


# ---------------- 核心逻辑 ----------------
def poll_new_listings() -> list[dict[str, Any]]:
    """拉取 OKX 所有 SWAP 合约，返回当天新 listing（USDT 结算）。"""
    result = public_api().get_instruments(instType="SWAP")
    insts = result.get("data") or []
    now_utc = datetime.now(timezone.utc)
    today_start = int(datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc).timestamp() * 1000)
    processed = load_processed()

    new_events: list[dict[str, Any]] = []
    for inst in insts:
        settle = inst.get("settleCcy", "")
        if settle != "USDT":
            continue
        list_time_ms = inst.get("listTime")
        if not list_time_ms:
            continue
        try:
            list_ts = int(list_time_ms)
        except (ValueError, TypeError):
            continue
        inst_id = inst.get("instId", "")
        if not inst_id:
            continue
        if inst_id in processed:
            continue
        # 只处理当天及之后 listing（历史事件跳过）
        if list_ts < today_start:
            continue
        new_events.append({
            "inst_id": inst_id,
            "list_time_ms": list_ts,
            "list_time_iso": datetime.fromtimestamp(list_ts / 1000, tz=timezone.utc).isoformat(),
            "state": inst.get("state", ""),
            "base_ccy": inst.get("baseCcy", ""),
            "ct_val": float(inst.get("ctVal") or 0),
            "min_sz": float(inst.get("minSz") or 0),
            "lever_max": float(inst.get("lever") or 0),
        })
    return new_events


def process_listing_event(
    event: dict[str, Any],
    strategy: ListingFadeStrategy,
) -> pd.DataFrame:
    """对单个 listing 事件运行策略信号，返回 trades DataFrame。"""
    inst_id = event["inst_id"]
    list_time_ms = event["list_time_ms"]
    list_dt = datetime.fromtimestamp(list_time_ms / 1000, tz=timezone.utc)
    list_date = list_dt.date()
    end_date = list_date + timedelta(days=2)

    logger.info(f"  downloading kline: {inst_id} [{list_date} → {end_date}]")
    try:
        klines = download_and_cache(inst_id, list_date, end_date, bar="1m")
    except ValueError as e:
        logger.warning(f"  download failed (ValueError): {e}")
        return pd.DataFrame()
    except Exception as e:
        logger.warning(f"  download failed: {type(e).__name__}: {e}")
        return pd.DataFrame()

    if klines.empty:
        logger.warning(f"  empty klines for {inst_id}")
        return pd.DataFrame()

    list_ts = pd.Timestamp(list_time_ms, unit="ms", tz="UTC")
    window_end = list_ts + timedelta(minutes=60)
    window = klines[(klines.index >= list_ts) & (klines.index < window_end)].copy()
    if len(window) < 6:
        logger.info(f"  window_too_short: {len(window)} bars (< 6)")
        return pd.DataFrame()

    event_df = pd.DataFrame([{
        "announcement_id": inst_id,
        "inst_id": inst_id,
        "listing_time": list_time_ms,
    }])
    signals = strategy.compute_signals(window, event_df)
    if signals.empty:
        logger.info(f"  no signal for {inst_id}")
        return pd.DataFrame()

    signals["symbol"] = inst_id
    signals["entry_ts"] = pd.to_datetime(signals["entry_ts"], utc=True)
    signals["exit_ts"] = pd.to_datetime(signals["exit_ts"], utc=True)
    signals["mode"] = "forward_test"
    signals["recorded_at"] = datetime.now(timezone.utc).isoformat()

    first_bar = window.iloc[0]
    evidence = {
        "inst_id": inst_id,
        "list_time_iso": event["list_time_iso"],
        "first_bar_open": float(first_bar["open"]),
        "first_bar_ts": str(window.index[0]),
        "pump_high_5min": float(window.iloc[:5]["high"].max()),
        "window_bars": len(window),
        "signal_count": len(signals),
        "signal": signals.iloc[0].to_dict() if not signals.empty else None,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    evi_path = EVIDENCE_DIR / f"{inst_id}_evidence.json"
    evi_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    logger.info(f"  signal generated for {inst_id} → evidence saved ({len(signals)} signal(s))")
    return signals


def run_once() -> None:
    """单次扫描：检测新 listing → 运行信号 → 保存证据。"""
    logger.info("=" * 60)
    logger.info("listing_fade 前向监测器 — 单次扫描开始")
    logger.info(f"时间: {datetime.now(timezone.utc).isoformat()}")

    strategy = ListingFadeStrategy()
    new_events = poll_new_listings()
    logger.info(f"检测到 {len(new_events)} 个新 listing 事件")

    if not new_events:
        logger.info("无新事件，扫描结束")
        return

    all_trades: list[pd.DataFrame] = []
    processed = load_processed()
    now_iso = datetime.now(timezone.utc).isoformat()

    for event in new_events:
        inst_id = event["inst_id"]
        logger.info(f"处理: {inst_id}  listing_time={event['list_time_iso']}")
        trades = process_listing_event(event, strategy)
        if not trades.empty:
            all_trades.append(trades)
        processed[inst_id] = {
            "list_time_ms": str(event["list_time_ms"]),
            "list_time_iso": event["list_time_iso"],
            "processed_at": now_iso,
            "signal_generated": str(not trades.empty),
        }

    save_processed(processed)
    logger.info(f"processed_events.json 已更新 ({len(processed)} 个事件总计)")

    if all_trades:
        combined = pd.concat(all_trades, ignore_index=True)
        append_trades(combined)
        logger.info(f"本批次产生 {len(combined)} 笔信号")
    else:
        logger.info("本批次无信号产生")

    logger.info("单次扫描完成")


def run_loop(interval_minutes: int = 5) -> None:
    """持续轮询模式。"""
    logger.info(f"启动持续轮询模式，间隔={interval_minutes} 分钟")
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error(f"扫描异常: {type(e).__name__}: {e}")
        logger.info(f"等待 {interval_minutes} 分钟后下一轮扫描...")
        time.sleep(interval_minutes * 60)


# ---------------- CLI ----------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Edge A listing_fade 前向监测器")
    parser.add_argument("--once", action="store_true", help="单次运行后退出（默认：连续轮询）")
    parser.add_argument("--interval", type=int, default=5, help="轮询间隔（分钟），默认 5")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_loop(args.interval)


if __name__ == "__main__":
    main()
