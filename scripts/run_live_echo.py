"""V3 Live Echo Runner — OKX 实盘 C/D ensemble 运行器.

直接连接 OKX（OKX_FLAG 控制实盘/模拟盘），带 RiskGuard 风控闸门。
所有外网请求通过本地代理，代理配置见 src/okx_sdk.py 与 docs/architecture/sys-proxy-rules.md。

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
from src.okx_sdk import account_api, market_api, trade_api
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

# 治理：仓位名义价值 = 账户权益 × NOTIONAL_MULTIPLE（真实敞口的唯一风险旋钮）。
# 交易所杠杆与此解耦——每个合约的交易所杠杆统一设为该合约支持的最大值，
# 仅为降低保证金占用、让小资金也能开出仓位；实际敞口由 NOTIONAL_MULTIPLE 控制。
# 决策记录见 docs/design/2026-06-26-live-echo-runner.md §4。禁止漂移回 MAX_LEVERAGE=1。
NOTIONAL_MULTIPLE = 10

# 治理：同时持仓上限。小资金快速复利目标——集中而非分散。
# 每轮按信号 score 降序取 top-N（已有持仓计入名额），其余信号跳过。
# 理由：相关性极高的同向 alt 仓位并非分散，而是 N 倍手续费的同一 beta 下注；
# 单笔 round-trip 手续费≈名义×0.1%，多开会把 $3 级别本金快速磨光。
# 决策记录见 docs/design/2026-06-26-live-echo-runner.md §4.6。
MAX_CONCURRENT_POSITIONS = 2


def fmt_sz(sz: float) -> str:
    """将下单张数格式化为 OKX 接受的字符串（去除多余末尾零）."""
    s = f"{sz:.8f}".rstrip("0").rstrip(".")
    return s or "0"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {
        "session_start": "",
        "cycle_count": 0,
        "total_trades": 0,
        "peak_equity": 0.0,
        "sltp_pending": False,
    }


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
    """返回 {instId: {ctVal, lotSz, minSz, ctMult, maxLever}}."""
    result = account_api().get_instruments(instType="SWAP")
    insts = {}
    for i in result.get("data", []):
        ct_val = i.get("ctVal", "1")
        if not ct_val:
            continue
        insts[i["instId"]] = {
            "ctVal": float(ct_val),
            "lotSz": float(i.get("lotSz", "1")),
            "minSz": float(i.get("minSz", i.get("lotSz", "1"))),
            "ctMult": float(i.get("ctMult", "1")),
            "maxLever": int(float(i.get("lever", "1"))),
        }
    return insts


def get_ticker_prices() -> dict[str, float]:
    result = market_api().get_tickers(instType="SWAP")
    prices = {}
    for t in result.get("data", []):
        last = t.get("last", "")
        if last:
            prices[t["instId"]] = float(last)
    return prices


def compute_sz(inst_info: dict, equity: float, price: float) -> float:
    """按目标名义价值计算开仓张数。

    名义价值 = equity × NOTIONAL_MULTIPLE；单张名义 = ctVal × price。
    结果向下对齐到 lotSz 网格，且不低于 minSz；不足 minSz 则返回 0（跳过该合约）。
    """
    if price <= 0:
        return 0.0
    ct_val = inst_info["ctVal"]
    lot_sz = inst_info.get("lotSz", 1.0)
    min_sz = inst_info.get("minSz", lot_sz)
    target_notional = equity * NOTIONAL_MULTIPLE
    raw_sz = target_notional / (ct_val * price)
    # 向下对齐到 lotSz 网格
    sz = (int(raw_sz / lot_sz)) * lot_sz if lot_sz > 0 else raw_sz
    if sz < min_sz:
        return 0.0
    return sz


def find_valid_symbols(inst_map: dict, equity: float, prices: dict[str, float]) -> set[str]:
    valid = set()
    for inst_id in OKX_INST_IDS:
        info = inst_map.get(inst_id)
        if info is None:
            continue
        price = prices.get(inst_id, 0.0)
        if compute_sz(info, equity, price) > 0:
            valid.add(inst_id)
    return valid


def setup_leverage(inst_map: dict[str, dict], valid_symbols: set[str]) -> None:
    """将每个合约的交易所杠杆设为该合约支持的最大值（降低保证金占用）。

    实际开仓敞口由 compute_sz 按 NOTIONAL_MULTIPLE 独立控制，与此处杠杆解耦。
    """
    for inst_id in valid_symbols:
        info = inst_map.get(inst_id)
        if not info:
            continue
        lev = info.get("maxLever", 1)
        try:
            result = account_api().set_leverage(
                instId=inst_id,
                lever=str(lev),
                mgnMode="cross",
            )
            if result.get("code") == "0":
                logger.info(f"  {inst_id}: 杠杆上限设为 {lev}x")
                info["lever"] = lev
            else:
                logger.warning(f"  {inst_id}: 设置杠杆失败 {result.get('msg', '')}")
        except Exception as e:
            logger.warning(f"  {inst_id}: 设置杠杆异常: {e}")


def place_market_entry(inst_id: str, side: str, sz: float, pos_side: str) -> str | None:
    """市价开仓；成功返回 ordId，失败返回 None。"""
    logger.info(f"  开仓: {inst_id} {side} sz={fmt_sz(sz)} posSide={pos_side}")
    result = trade_api().place_order(
        instId=inst_id,
        tdMode="cross",
        side=side,
        posSide=pos_side,
        ordType="market",
        sz=fmt_sz(sz),
    )
    if result.get("code") == "0":
        ord_id = result.get("data", [{}])[0].get("ordId", "") or ""
        logger.info(f"  开仓成功: ordId={ord_id or '?'}")
        return ord_id or None
    logger.warning(f"  开仓失败: {result.get('msg', '')} (full={result})")
    return None


def place_market_close(inst_id: str, side: str, sz: float, pos_side: str) -> bool:
    logger.info(f"  平仓: {inst_id} {side} sz={fmt_sz(sz)} posSide={pos_side}")
    result = trade_api().place_order(
        instId=inst_id,
        tdMode="cross",
        side=side,
        posSide=pos_side,
        ordType="market",
        sz=fmt_sz(sz),
        reduceOnly=True,
    )
    if result.get("code") == "0":
        logger.info(f"  平仓成功: ordId={result.get('data', [{}])[0].get('ordId', '?')}")
        return True
    logger.warning(f"  平仓失败: {result.get('msg', '')} (full={result})")
    return False


def get_fill_px(inst_id: str, ord_id: str, retries: int = 5, delay: float = 0.3) -> float | None:
    """按 ordId 查询订单成交均价 avgPx，带重试。

    市价单成交后，订单记录的 avgPx 是权威成交价；直接查 /trade/fills 常因
    撮合结果尚未入索引而返回空。这里按 ordId 轮询订单详情，避免该竞态。
    """
    if not ord_id:
        return None
    for attempt in range(retries):
        result = trade_api().get_order(instId=inst_id, ordId=ord_id)
        if result.get("code") == "0" and result.get("data"):
            avg_px = result["data"][0].get("avgPx", "")
            if avg_px and float(avg_px) > 0:
                return float(avg_px)
        if attempt < retries - 1:
            time.sleep(delay)
    return None


def attach_sltp_via_algo_order(
    inst_id: str,
    side: str,
    pos_side: str,
    sz: float,
    fill_px: float,
    stop_price: float,
    target_price: float,
) -> bool:
    """根据实际成交价独立挂 SL/TP algo 单（reduceOnly=True）."""
    if side == "buy":
        if not (stop_price < fill_px and target_price > fill_px):
            logger.warning(
                f"  {inst_id} 做多 SL/TP 方向校验失败: fill={fill_px:.4f}, SL={stop_price:.4f}, TP={target_price:.4f}"
            )
            return False
    else:  # side == "sell"
        if not (stop_price > fill_px and target_price < fill_px):
            logger.warning(
                f"  {inst_id} 做空 SL/TP 方向校验失败: fill={fill_px:.4f}, SL={stop_price:.4f}, TP={target_price:.4f}"
            )
            return False

    close_side = "sell" if side == "buy" else "buy"
    logger.info(f"  挂 SL/TP: {inst_id} fill={fill_px:.4f} SL={stop_price:.4f} TP={target_price:.4f}")
    result = trade_api().place_algo_order(
        instId=inst_id,
        tdMode="cross",
        side=close_side,
        posSide=pos_side,
        ordType="oco",
        sz=fmt_sz(sz),
        reduceOnly=True,
        slTriggerPx=str(round(stop_price, 4)),
        slOrdPx="-1",
        tpTriggerPx=str(round(target_price, 4)),
        tpOrdPx="-1",
    )
    if result.get("code") == "0":
        logger.info(f"  SL/TP 挂载成功: algoId={result.get('data', [{}])[0].get('algoId', '?')}")
        return True
    logger.warning(f"  SL/TP 挂载失败: {result.get('msg', '')} (full={result})")
    return False


def execute_entries(
    signals: pd.DataFrame,
    open_positions: dict,
    inst_map: dict,
    equity: float,
    prices: dict[str, float],
    risk_guard: RiskGuard,
) -> list[dict]:
    state = load_state()
    if state.get("sltp_pending"):
        logger.info("  SL/TP 挂载待完成，跳过新仓")
        return []

    # 同时持仓上限：已有持仓计入名额，剩余名额按 score 降序分配
    slots = MAX_CONCURRENT_POSITIONS - len(open_positions)
    if slots <= 0:
        logger.info(f"  持仓已达上限 {MAX_CONCURRENT_POSITIONS}，跳过开仓")
        return []

    # resolve_conflicts 会按 entry_ts/priority 重排，这里按 score 降序还原以取 top-N
    if "score" in signals.columns:
        signals = signals.sort_values("score", ascending=False)

    opened = []
    for _, sig in signals.iterrows():
        if len(opened) >= slots:
            logger.info(f"  已开 {len(opened)} 仓，达本轮名额上限 {slots}")
            break
        symbol = sig.get("symbol", "")
        inst_id = next((k for k, v in SYMBOL_MAP.items() if v == symbol), None)
        if inst_id is None:
            continue
        if inst_id in open_positions:
            logger.info(f"  {symbol}: 已有持仓，跳过开仓")
            continue

        info = inst_map.get(inst_id)
        if info is None:
            continue
        price = prices.get(inst_id, 0.0)
        sz = compute_sz(info, equity, price)
        if sz <= 0:
            continue

        signal_dir = sig.get("signal", 0)
        is_long = signal_dir == 1
        side = "buy" if is_long else "sell"
        pos_side = "long" if is_long else "short"
        edge = sig.get("edge", "?")

        stop_px = float(sig.get("stop_price", 0))
        target_px = float(sig.get("target_price", 0))

        logger.info(f"  {symbol} ({edge}): dir={signal_dir}, sz={sz} SL={stop_px:.4f} TP={target_px:.4f}")

        # 开仓前用实时价校验 SL/TP 方向：信号 entry_price 取自 1h 收盘价，
        # 市价成交时价格可能已穿越 TP/SL（均值回归已发生）。此时开仓只会立即
        # 触发反向校验失败 + 平仓，白付一次 round-trip 手续费——直接跳过。
        if price > 0:
            if is_long and not (stop_px < price < target_px):
                logger.info(f"  {symbol}: 实时价 {price:.4f} 已脱离做多区间 (SL={stop_px:.4f}, TP={target_px:.4f})，跳过")
                continue
            if not is_long and not (target_px < price < stop_px):
                logger.info(f"  {symbol}: 实时价 {price:.4f} 已脱离做空区间 (TP={target_px:.4f}, SL={stop_px:.4f})，跳过")
                continue

        ord_id = place_market_entry(inst_id, side, sz, pos_side)
        if ord_id is None:
            continue

        state = load_state()
        state["sltp_pending"] = True
        save_state(state)

        fill_px = get_fill_px(inst_id, ord_id)
        sltp_ok = False
        if fill_px is not None and fill_px > 0:
            sltp_ok = attach_sltp_via_algo_order(
                inst_id=inst_id,
                side=side,
                pos_side=pos_side,
                sz=sz,
                fill_px=fill_px,
                stop_price=stop_px,
                target_price=target_px,
            )
        else:
            logger.warning(f"  {inst_id}: 无法获取成交价，持仓暂无交易所 SL/TP 保护")

        if not sltp_ok:
            # 无法挂 SL/TP 的持仓立即平仓，避免无保护裸奔；同时释放 pending 标志
            logger.warning(f"  {inst_id}: SL/TP 挂载失败，立即平仓")
            close_side = "sell" if side == "buy" else "buy"
            place_market_close(inst_id, close_side, sz, pos_side)
            state = load_state()
            state["sltp_pending"] = False
            save_state(state)
            continue

        state = load_state()
        state["sltp_pending"] = False
        save_state(state)

        opened.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "action": f"enter_{'long' if is_long else 'short'}",
            "price": fill_px,
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

    min_equity = max(equity * 0.5, 1.0)
    if equity < min_equity:
        logger.error(f"  权益不足 ${min_equity:.2f} (当前 ${equity:.2f})")
        sys.exit(1)

    inst_map = get_instrument_map()
    prices = get_ticker_prices()
    valid = find_valid_symbols(inst_map, equity, prices)
    logger.info(f"  可交易 symbols: {len(valid)}/{len(OKX_INST_IDS)}")
    if not valid:
        raise RuntimeError("无可交易合约")

    setup_leverage(inst_map, valid)
    return equity, inst_map


def run_once(inst_map: dict, risk_guard: RiskGuard) -> None:
    logger.info("-" * 40)

    if risk_guard.is_halted:
        logger.warning(f"  风控触发: {risk_guard.halted_by}")
        return

    equity = get_equity()
    signals = compute_ensemble_signals(equity=equity, risk_guard=risk_guard)
    if signals.empty:
        logger.info("  ensemble 无信号")
        return

    positions = get_positions()
    logger.info(f"  权益: ${equity:.2f} | 持仓: {len(positions)} 个")

    prices = get_ticker_prices()
    opened = execute_entries(signals, positions, inst_map, equity, prices, risk_guard)
    if opened:
        append_trades(pd.DataFrame(opened))

    state = load_state()
    state["cycle_count"] += 1
    state["total_trades"] += len(opened)
    if equity > state.get("peak_equity", 0):
        state["peak_equity"] = round(equity, 4)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    for o in opened:
        logger.info(f"  ENTER {o['symbol']} {o['action']} ({o['reason']})")


def run_loop(interval_seconds: int = 60) -> None:
    inst_map = {}
    state = load_state()
    state["session_start"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    risk_guard: RiskGuard | None = None

    while True:
        try:
            if not inst_map:
                equity, inst_map = startup_check()
                if not inst_map:
                    inst_map = {}
                    raise RuntimeError("startup_check 失败")
                risk_guard = RiskGuard()
                risk_guard.update_equity(equity)
            run_once(inst_map, risk_guard)
        except Exception as e:
            logger.error(f"  异常: {type(e).__name__}: {e}")
            inst_map = {}

        if risk_guard is not None and risk_guard.is_halted:
            logger.warning(f"风控触发 ({risk_guard.halted_by})，运行停止")
            state = load_state()
            state["halted"] = True
            state["halt_reason"] = risk_guard.halted_by
            save_state(state)
            break

        logger.info(f"  等待 {interval_seconds}s ...")
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="V3 Live Echo — 实盘 C/D ensemble")
    parser.add_argument("--once", action="store_true", help="单次运行后退出")
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔 (秒)")
    args = parser.parse_args()
    if args.once:
        try:
            equity, inst_map = startup_check()
            risk_guard = RiskGuard()
            risk_guard.update_equity(equity)
            run_once(inst_map, risk_guard)
        except Exception as e:
            logger.error(f"  异常: {type(e).__name__}: {e}")
    else:
        run_loop(args.interval)


if __name__ == "__main__":
    main()
