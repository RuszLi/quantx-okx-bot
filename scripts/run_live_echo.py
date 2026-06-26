"""V3 Live Echo Runner — OKX 主网 $7 实盘 C/D ensemble 运行器.

直接连接 OKX 主网（OKX_FLAG=0），无模拟盘过渡。
所有外网请求通过本地代理 http://127.0.0.1:7890。

用法:
    python scripts/run_live_echo.py              # 持续轮询 (60s)
    python scripts/run_live_echo.py --once       # 单次运行
    python scripts/run_live_echo.py --interval 30 # 30 秒轮询
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.live.risk_guard import RiskGuard
from src.okx_sdk import account_api, public_api, trade_api
from src.paper.pipeline import (
    OKX_INST_IDS,
    SYMBOL_MAP,
    compute_ensemble_signals,
    validate_symbols,
)

LIVE_ROOT = ROOT / "data" / "live_echo"
TRADES_PATH = LIVE_ROOT / "trades.csv"
STATE_PATH = LIVE_ROOT / "state.json"
LOG_PATH = LIVE_ROOT / "runner.log"

LIVE_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(str(LOG_PATH), encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("live_echo")

STOP_LOSS_USDT = -0.21
TAKE_PROFIT_USDT = 0.42
TIME_STOP_HOURS = 5
MAX_LEVERAGE = 1


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"session_start": "", "cycle_count": 0, "total_trades": 0, "peak_equity": 0.0, "halted": False, "halt_reason": None}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def append_trades(new_rows: pd.DataFrame) -> None:
    existing = pd.read_csv(TRADES_PATH) if TRADES_PATH.exists() else pd.DataFrame()
    combined = pd.concat([existing, new_rows], ignore_index=True) if not existing.empty else new_rows
    combined.to_csv(TRADES_PATH, index=False)


def get_positions() -> dict[str, dict]:
    result = account_api().get_positions()
    if result.get("code") != "0":
        logger.warning(f"  get_positions 失败: {result.get('msg', '')}")
        return {}
    positions = {}
    for p in result.get("data", []):
        inst_id = p["instId"]
        pos = float(p.get("pos", "0"))
        if pos == 0:
            continue
        positions[inst_id] = {
            "pos": pos,
            "upl": float(p.get("upl", "0")),
            "avgPx": float(p.get("avgPx", "0")),
            "cTime": int(p.get("cTime", "0")),
        }
    return positions


def get_equity() -> float:
    result = account_api().get_account_balance()
    if result.get("code") == "0" and result.get("data"):
        return float(result["data"][0].get("totalEq", "0"))
    return 0.0


def get_instrument_map() -> dict[str, dict]:
    result = public_api().get_instruments(instType="SWAP")
    insts = {}
    for i in result.get("data", []):
        insts[i["instId"]] = {
            "ctVal": float(i.get("ctVal", "1")),
            "lotSz": float(i.get("lotSz", "1")),
        }
    return insts


def compute_sz(info: dict, equity: float) -> int:
    max_notional = equity * MAX_LEVERAGE
    sz = int(max_notional / info["ctVal"])
    lot_sz = int(info["lotSz"])
    return sz if sz >= lot_sz else 0


def find_valid_symbols(inst_map: dict, equity: float) -> set[str]:
    return {i for i in OKX_INST_IDS if inst_map.get(i) and compute_sz(inst_map[i], equity) > 0}


def place_market_order(inst_id: str, side: str, sz: int) -> bool:
    logger.info(f"  下单: {inst_id} {side} sz={sz}")
    result = trade_api().place_order(
        instId=inst_id,
        tdMode="cross",
        side=side,
        posSide="net",
        ordType="market",
        sz=str(sz),
    )
    if result.get("code") == "0":
        logger.info(f"  ✅ 成功: ordId={result.get('data', [{}])[0].get('ordId', '?')}")
        return True
    logger.warning(f"  ❌ 失败: {result.get('msg', '')}")
    return False


def check_exits(positions: dict[str, dict], risk_guard: RiskGuard) -> list[dict]:
    closed = []
    for inst_id, pos in positions.items():
        upl = pos["upl"]
        entry_time = datetime.fromtimestamp(pos["cTime"] / 1000, tz=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600

        reason = None
        if upl <= STOP_LOSS_USDT:
            reason = "stop_loss"
        elif upl >= TAKE_PROFIT_USDT:
            reason = "take_profit"
        elif age_hours >= TIME_STOP_HOURS:
            reason = "time_stop"

        if reason is None:
            continue

        side = "sell" if pos["pos"] > 0 else "buy"
        sz = int(abs(pos["pos"]))
        logger.info(f"  退出: {inst_id} {reason} upl={upl:.2f} age={age_hours:.1f}h")
        if place_market_order(inst_id, side, sz):
            equity = get_equity()
            risk_guard.update_equity(equity, trade_pnl_r=upl)
            closed.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": SYMBOL_MAP.get(inst_id, inst_id),
                "action": f"exit_{'long' if pos['pos'] > 0 else 'short'}",
                "price": pos["avgPx"],
                "sz": sz,
                "pnl": round(upl, 4),
                "reason": reason,
            })
    return closed


def execute_entries(signals: pd.DataFrame, open_positions: dict, inst_map: dict, equity: float) -> list[dict]:
    opened = []
    for _, sig in signals.iterrows():
        symbol = sig.get("symbol", "")
        inst_id = next((k for k, v in SYMBOL_MAP.items() if v == symbol), None)
        if inst_id is None:
            continue

        if inst_id in open_positions:
            continue

        info = inst_map.get(inst_id)
        if info is None:
            continue
        sz = compute_sz(info, equity)
        if sz <= 0:
            continue

        signal_dir = sig.get("signal", 0)
        side = "buy" if signal_dir == 1 else "sell"
        edge = sig.get("edge", "?")

        logger.info(f"  {symbol} ({edge}): dir={signal_dir}, sz={sz}")
        if place_market_order(inst_id, side, sz):
            opened.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "action": f"enter_{'long' if signal_dir == 1 else 'short'}",
                "price": sig.get("entry_price", 0.0),
                "sz": sz,
                "pnl": 0.0,
                "reason": f"ensemble_{edge}",
            })
    return opened


def startup_check() -> tuple[float, dict]:
    validate_symbols()
    logger.info("=" * 50)
    logger.info("Live Echo Runner 启动")
    logger.info("=" * 50)

    equity = get_equity()
    logger.info(f"  OKX 账户权益: ${equity:.2f}")
    if equity < 7.0:
        logger.error(f"  权益不足 $7 (当前 ${equity:.2f})")
        sys.exit(1)

    inst_map = get_instrument_map()
    valid = find_valid_symbols(inst_map, equity)
    logger.info(f"  可交易 symbols: {len(valid)}/{len(OKX_INST_IDS)}")
    if not valid:
        logger.error("  无可交易合约")
        sys.exit(1)

    return equity, inst_map


def run_once(inst_map: dict, risk_guard: RiskGuard) -> None:
    logger.info("─" * 40)

    signals = compute_ensemble_signals()
    if signals.empty:
        logger.info("  ensemble 无信号")
        return

    positions = get_positions()
    equity = get_equity()
    logger.info(f"  权益: ${equity:.2f} | 持仓: {len(positions)} 个")

    if risk_guard.is_halted:
        logger.warning(f"  ⛔ 风控: {risk_guard.halted_by}")
        return

    closed = check_exits(positions, risk_guard)
    if closed:
        append_trades(pd.DataFrame(closed))

    opened = execute_entries(signals, positions, inst_map, equity)
    if opened:
        append_trades(pd.DataFrame(opened))

    state = load_state()
    state["cycle_count"] += 1
    state["total_trades"] += len(closed) + len(opened)
    if equity > state.get("peak_equity", 0):
        state["peak_equity"] = round(equity, 4)
    if risk_guard.is_halted:
        state["halted"] = True
        state["halt_reason"] = risk_guard.halted_by
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    for c in closed:
        logger.info(f"  ⬅ {c['symbol']} {c['action']} pnl={c['pnl']} ({c['reason']})")
    for o in opened:
        logger.info(f"  ➡ {o['symbol']} {o['action']} ({o['reason']})")


def run_loop(interval_seconds: int = 60) -> None:
    equity, inst_map = startup_check()
    risk_guard = RiskGuard()
    risk_guard.update_equity(equity)

    state = load_state()
    state["session_start"] = datetime.now(timezone.utc).isoformat()
    state["halted"] = False
    state["halt_reason"] = None
    save_state(state)

    while True:
        try:
            run_once(inst_map, risk_guard)
        except Exception as e:
            logger.error(f"  ❌ 异常: {type(e).__name__}: {e}")

        if risk_guard.is_halted:
            logger.warning(f"⛔ 风控触发 ({risk_guard.halted_by})，停止运行")
            state = load_state()
            state["halted"] = True
            state["halt_reason"] = risk_guard.halted_by
            save_state(state)
            break

        logger.info(f"  等待 {interval_seconds}s ...")
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="V3 Live Echo — $7 实盘 C/D ensemble")
    parser.add_argument("--once", action="store_true", help="单次运行后退出")
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔 (秒)")
    args = parser.parse_args()
    if args.once:
        equity, inst_map = startup_check()
        risk_guard = RiskGuard()
        risk_guard.update_equity(equity)
        run_once(inst_map, risk_guard)
    else:
        run_loop(args.interval)


if __name__ == "__main__":
    main()
