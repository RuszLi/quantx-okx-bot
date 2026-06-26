"""V3 纸交易 ensemble runner — 连接 OKX 实时 1h kline, 运行 C/D ensemble 信号并记录.

用法:
    python scripts/run_paper_ensemble.py --once
    python scripts/run_paper_ensemble.py
    python scripts/run_paper_ensemble.py --interval 60
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.live.risk_guard import RiskGuard
from src.paper.pipeline import append_csv, compute_ensemble_signals, validate_symbols

PAPER_ROOT = ROOT / "data" / "paper_ensemble"
ENSEMBLE_PATH = PAPER_ROOT / "ensemble.csv"
STATE_PATH = PAPER_ROOT / "runner_state.json"
LOG_PATH = PAPER_ROOT / "runner.log"

PAPER_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(str(LOG_PATH), encoding="utf-8"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("paper_ensemble")


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"cycle_count": 0, "total_ensemble": 0, "last_run": ""}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_once(risk_guard: RiskGuard | None = None) -> None:
    state = load_state()
    state["cycle_count"] += 1
    now_iso = datetime.now(timezone.utc).isoformat()
    logger.info(f"[Cycle {state['cycle_count']}] 开始 — {now_iso}")

    validate_symbols()
    result = compute_ensemble_signals(equity=7.0, risk_guard=risk_guard)

    if result.empty:
        logger.info("  ensemble 无输出")
        state["last_run"] = now_iso
        save_state(state)
        return

    result["recorded_at"] = now_iso
    result["mode"] = "paper"

    append_csv(ENSEMBLE_PATH, result)

    c_count = int((result["edge"] == "C").sum())
    d_count = int((result["edge"] == "D").sum())
    state["total_ensemble"] += len(result)
    state["last_run"] = now_iso
    save_state(state)
    logger.info(f"  Ensemble 输出 {len(result)} 笔 (C={c_count}, D={d_count})")


def run_loop(interval_minutes: int = 60) -> None:
    logger.info(f"启动持续轮询模式，间隔={interval_minutes} 分钟")
    risk_guard = RiskGuard()
    risk_guard.update_equity(7.0)
    while True:
        try:
            run_once(risk_guard=risk_guard)
        except Exception as e:
            logger.error(f"扫描异常: {type(e).__name__}: {e}")

        if risk_guard.is_halted:
            logger.warning(f"风控触发 ({risk_guard.halted_by})，停止运行")
            break

        time.sleep(interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="V3 纸交易 ensemble runner")
    parser.add_argument("--once", action="store_true", help="单次运行后退出")
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔 (分钟)")
    args = parser.parse_args()
    if args.once:
        risk_guard = RiskGuard()
        risk_guard.update_equity(7.0)
        run_once(risk_guard=risk_guard)
    else:
        run_loop(args.interval)


if __name__ == "__main__":
    main()
