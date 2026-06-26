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

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.paper.pipeline import compute_ensemble_signals, validate_symbols

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


def run_once() -> None:
    state = load_state()
    state["cycle_count"] += 1
    now_iso = datetime.now(timezone.utc).isoformat()
    logger.info(f"[Cycle {state['cycle_count']}] 开始 — {now_iso}")

    validate_symbols()
    result = compute_ensemble_signals()

    if result.empty:
        logger.info("  ensemble 无输出")
        state["last_run"] = now_iso
        save_state(state)
        return

    result["recorded_at"] = now_iso
    result["mode"] = "paper"

    existing = load_csv(ENSEMBLE_PATH) if ENSEMBLE_PATH.exists() else None
    combined = pd.concat([existing, result], ignore_index=True) if existing is not None else result
    combined.to_csv(ENSEMBLE_PATH, index=False)

    c_count = int((result["edge"] == "C").sum())
    d_count = int((result["edge"] == "D").sum())
    state["total_ensemble"] += len(result)
    state["last_run"] = now_iso
    save_state(state)
    logger.info(f"  Ensemble 输出 {len(result)} 笔 (C={c_count}, D={d_count})")


def load_csv(path):
    import pandas as pd
    return pd.read_csv(path)


def run_loop(interval_minutes: int = 60) -> None:
    logger.info(f"启动持续轮询模式，间隔={interval_minutes} 分钟")
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error(f"扫描异常: {type(e).__name__}: {e}")
        time.sleep(interval_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="V3 纸交易 ensemble runner")
    parser.add_argument("--once", action="store_true", help="单次运行后退出")
    parser.add_argument("--interval", type=int, default=60, help="轮询间隔 (分钟)")
    args = parser.parse_args()
    if args.once:
        run_once()
    else:
        run_loop(args.interval)


if __name__ == "__main__":
    main()
