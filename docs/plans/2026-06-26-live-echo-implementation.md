# Live Echo Runner 实现计划

> **状态：** 已完成 (2026-06-26)
> **commit:** 1b99b3a

> **面向 AI 代理的工作者：** 此计划由当前会话内联执行，无需子代理调度。

**目标：** 创建 `scripts/run_live_echo.py`，以 $7 实盘运行 C/D ensemble 信号，覆盖信号计算、OKX 下单、持仓跟踪、退出管理、风控、持久化全链路。

**架构：** 提取信号管道到共享模块 `src/paper/pipeline.py`，纸交易脚本和实盘脚本共同引用。实盘脚本在 60 秒循环中执行：获取 kline → 计算信号 → 开仓 → 管持仓 → 检查退出 → 持久化。

**技术栈：** Python, `python-okx`, pandas, `src/paper/pipeline.py`（新建），`src/live/risk_guard.py`（现有）

---

### 任务 1：提取共享信号管道

**文件：**
- 新建：`src/paper/pipeline.py`
- 修改：`scripts/run_paper_ensemble.py`（任务 2）

- [ ] **步骤 1：创建 `src/paper/pipeline.py`**

```python
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

# ── 常量 ──────────────────────────────────────────────

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

# ── SDK 客户端 ────────────────────────────────────────

_CLIENT = market_api()
_VALIDATED = False


# ── 网络请求封装 ──────────────────────────────────────

def _okx_req(fn, *args, **kwargs):
    for wait in _RETRY_SLEEP:
        try:
            return fn(*args, **kwargs)
        except Exception:
            time.sleep(wait)
    return fn(*args, **kwargs)


# ── Kline ─────────────────────────────────────────────

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


# ── 特征构造 ──────────────────────────────────────────

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


# ── Symbol 校验 ───────────────────────────────────────

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


# ── 持久化辅助 ────────────────────────────────────────

def load_csv(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def append_csv(path: Path, new_rows: pd.DataFrame) -> None:
    existing = load_csv(path)
    combined = pd.concat([existing, new_rows], ignore_index=True) if not existing.empty else new_rows
    combined.to_csv(path, index=False)


# ── 完整信号管道 ──────────────────────────────────────

def compute_ensemble_signants(
    inst_ids: list[str] | None = None,
    equity: float = 7.0,
) -> pd.DataFrame:
    """一键计算所有 symbols 的 C/D ensemble 信号.

    流程: validate → fetch kline → C 特征 → C 信号 → D 特征 → D 信号 → ensemble → risk guard → 返回.
    """
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
```

- [ ] **步骤 2：运行导入检查**

```bash
python -c "from src.paper.pipeline import compute_ensemble_signants, fetch_1h_candles; print('pipeline OK')"
```

预期输出：`pipeline OK`

- [ ] **步骤 3：Commit**

```bash
git add src/paper/pipeline.py
git commit -m "feat: extract shared signal pipeline to src/paper/pipeline.py"
```

---

### 任务 2：重写 paper_ensemble 引用 pipeline

**文件：**
- 修改：`scripts/run_paper_ensemble.py`

- [ ] **步骤 1：重写 `scripts/run_paper_ensemble.py`**

删除重复的常量、`_okx_req`、`fetch_recent_1h_candles`、`_rows_to_frame`、`build_beta_decouple_market_data`、`build_weekend_wick_market_data`、`_validate_symbols`、`load_csv`、`append_csv`、`load_state`、`save_state` 等函数，改为从 `pipeline` 导入。

保留的独有逻辑：
- runner state 持久化（`runner_state.json`）
- C/D 信号分别保存到 `signals_c.csv` / `signals_d.csv`
- `run_once()` / `run_loop()` / `main()` 控制流

```python
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

from src.paper.pipeline import (
    OKX_INST_IDS,
    SYMBOL_MAP,
    append_csv,
    compute_ensemble_signants,
    load_csv,
    validate_symbols,
)

# ── 配置 ──────────────────────────────────────────────

PAPER_ROOT = ROOT / "data" / "paper_ensemble"
C_SIGNALS_PATH = PAPER_ROOT / "signals_c.csv"
D_SIGNALS_PATH = PAPER_ROOT / "signals_d.csv"
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


# ── 持久化 ────────────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"cycle_count": 0, "total_signals_c": 0, "total_signals_d": 0, "total_ensemble": 0, "last_run": ""}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ── 核心逻辑 ──────────────────────────────────────────

def run_once() -> None:
    state = load_state()
    state["cycle_count"] += 1
    now_iso = datetime.now(timezone.utc).isoformat()
    logger.info(f"[Cycle {state['cycle_count']}] 开始 — {now_iso}")

    validate_symbols()
    result = compute_ensemble_signants()

    if result.empty:
        logger.info("  ensemble 无输出")
        state["last_run"] = now_iso
        save_state(state)
        return

    result["recorded_at"] = now_iso
    result["mode"] = "paper"
    append_csv(ENSEMBLE_PATH, result)

    # 统计
    c_count = int((result["edge"] == "C").sum())
    d_count = int((result["edge"] == "D").sum())
    state["total_ensemble"] += len(result)
    state["last_run"] = now_iso
    save_state(state)
    logger.info(f"  Ensemble 输出 {len(result)} 笔 (C={c_count}, D={d_count})")


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
```

- [ ] **步骤 2：运行语法检查**

```bash
python -c "import scripts.run_paper_ensemble; print('paper_ensemble OK')"
```

预期输出：`paper_ensemble OK`

- [ ] **步骤 3：运行 --once 确认功能正常**

```bash
python scripts/run_paper_ensemble.py --once
```

预期：无报错，日志输出完成信息

- [ ] **步骤 4：Commit**

```bash
git add scripts/run_paper_ensemble.py
git commit -m "refactor: paper_ensemble imports from pipeline.py"
```

---

### 任务 3：创建实盘运行器

**文件：**
- 新建：`scripts/run_live_echo.py`

- [ ] **步骤 1：创建 `scripts/run_live_echo.py`**

```python
"""V3 Live Echo Runner — OKX 主网 $7 实盘 C/D ensemble 运行器.

直接使用 OKX_FLAG=0（主网）连接实盘，无模拟盘过渡。

用法:
    # 确保 .env 中 OKX_FLAG=0, OKX_API_KEY/OKX_API_SECRET/OKX_PASSPHRASE 已配置
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
from src.okx_sdk import account_api, trade_api
from src.paper.pipeline import (
    OKX_INST_IDS,
    SYMBOL_MAP,
    compute_ensemble_signants,
    validate_symbols,
)

# ── 配置 ──────────────────────────────────────────────

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

# ── 退出参数 (基于 $7 equity) ─────────────────────────

STOP_LOSS_USDT = -0.21
TAKE_PROFIT_USDT = 0.42
TIME_STOP_HOURS = 5
MAX_LEVERAGE = 1


# ── 状态管理 ──────────────────────────────────────────

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"session_start": "", "cycle_count": 0, "total_trades": 0, "peak_equity": 0.0, "halted": False, "halt_reason": None}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def load_existing_trades() -> pd.DataFrame:
    if TRADES_PATH.exists():
        return pd.read_csv(TRADES_PATH)
    return pd.DataFrame()


def append_trades(new_rows: pd.DataFrame) -> None:
    existing = load_existing_trades()
    combined = pd.concat([existing, new_rows], ignore_index=True) if not existing.empty else new_rows
    combined.to_csv(TRADES_PATH, index=False)


# ── OKX 仓位工具 ──────────────────────────────────────

def get_positions() -> dict[str, dict]:
    """返回 {instId: {pos, upl, avgPx, cTime}} 格式的持仓字典."""
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
    """返回 {instId: {ctVal, lotSz, ctMult}}."""
    result = account_api().get_instruments(instType="SWAP")
    insts = {}
    for i in result.get("data", []):
        insts[i["instId"]] = {
            "ctVal": float(i.get("ctVal", "1")),
            "lotSz": float(i.get("lotSz", "1")),
            "ctMult": float(i.get("ctMult", "1")),
        }
    return insts


def compute_sz(inst_info: dict, equity: float) -> int:
    max_notional = equity * MAX_LEVERAGE
    ct_val = inst_info["ctVal"]
    lot_sz = int(inst_info["lotSz"])
    sz = int(max_notional / ct_val)
    if sz < lot_sz:
        return 0
    return sz


def find_valid_symbols(inst_map: dict, equity: float) -> set[str]:
    valid = set()
    for inst_id in OKX_INST_IDS:
        info = inst_map.get(inst_id)
        if info is None:
            continue
        if compute_sz(info, equity) > 0:
            valid.add(inst_id)
    return valid


# ── 下单 ──────────────────────────────────────────────

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
        logger.info(f"  ✅ 下单成功: {result.get('data', [{}])[0].get('ordId', '?')}")
        return True
    logger.warning(f"  ❌ 下单失败: {result.get('msg', '')}")
    return False


# ── 退出管理 ──────────────────────────────────────────

def check_exits(positions: dict[str, dict], risk_guard: RiskGuard) -> list[dict]:
    """检查持仓退出条件，返回已平仓的交易记录列表."""
    closed: list[dict] = []
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
        ok = place_market_order(inst_id, side, sz)
        if ok:
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


# ── 开仓处理 ──────────────────────────────────────────

def execute_entries(signals: pd.DataFrame, open_positions: dict, inst_map: dict, equity: float, risk_guard: RiskGuard) -> list[dict]:
    """执行 ensemble 信号的开仓指令."""
    opened: list[dict] = []
    for _, sig in signals.iterrows():
        symbol = sig.get("symbol", "")
        inst_id = [k for k, v in SYMBOL_MAP.items() if v == symbol]
        if not inst_id:
            continue
        inst_id = inst_id[0]

        # 已有持仓则跳过
        if inst_id in open_positions:
            logger.info(f"  {symbol}: 已有持仓, 跳过开仓")
            continue

        info = inst_map.get(inst_id)
        if info is None:
            continue
        sz = compute_sz(info, equity)
        if sz <= 0:
            logger.debug(f"  {symbol}: sz={sz} 跳过")
            continue

        signal_dir = sig.get("signal", 0)
        side = "buy" if signal_dir == 1 else "sell"
        edge = sig.get("edge", "?")

        logger.info(f"  {symbol} ({edge}): signal={signal_dir}, sz={sz}")
        ok = place_market_order(inst_id, side, sz)
        if ok:
            equity = get_equity()
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


# ── 启动验证 ──────────────────────────────────────────

def startup_check() -> tuple[float, dict]:
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


# ── 主循环 ────────────────────────────────────────────

def run_once(inst_map: dict, risk_guard: RiskGuard) -> None:
    logger.info("─" * 40)

    signals = compute_ensemble_signants()
    if signals.empty:
        logger.info("  ensemble 无信号")
        return

    positions = get_positions()
    equity = get_equity()
    logger.info(f"  权益: ${equity:.2f} | 持仓: {len(positions)} 个")

    if risk_guard.is_halted:
        logger.warning(f"  ⛔ 风控触发: {risk_guard.halted_by}")
        return

    # 先检查退出
    closed = check_exits(positions, risk_guard)
    if closed:
        append_trades(pd.DataFrame(closed))

    # 再执行开仓
    opened = execute_entries(signals, positions, inst_map, equity, risk_guard)
    if opened:
        append_trades(pd.DataFrame(opened))

    # 更新状态
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

    if closed:
        for c in closed:
            logger.info(f"  ⬅ {c['symbol']} {c['action']} pnl={c['pnl']} ({c['reason']})")
    if opened:
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
            logger.error(f"  ❌ 运行异常: {type(e).__name__}: {e}")

        if risk_guard.is_halted:
            logger.warning(f"⛔ 风控触发 ({risk_guard.halted_by})，运行停止")
            state = load_state()
            state["halted"] = True
            state["halt_reason"] = risk_guard.halted_by
            save_state(state)
            break

        logger.info(f"  等待 {interval_seconds}s 后下一轮...")
        time.sleep(interval_seconds)


# ── CLI ───────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="V3 Live Echo — $7 实盘 C/D ensemble")
    parser.add_argument("--once", action="store_true", help="单次运行")
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
```

- [ ] **步骤 2：运行语法检查**

```bash
python -c "import scripts.run_live_echo; print('live_echo OK')"
```

预期输出：`live_echo OK`

- [ ] **步骤 3：Commit**

```bash
git add scripts/run_live_echo.py
git commit -m "feat: add live echo runner for $7 real trading"
```

---

## 自检

- [ ] 设计文档中每个功能点都有对应实现任务
- [ ] 无占位符 / TODO / "添加适当错误处理"
- [ ] 无重复代码（管道已提取到 pipeline.py）
- [ ] 信号管道在 paper 和 live 间一致
- [ ] 所有文件路径使用正斜杠
- [ ] 代码遵循现有项目命名风格
