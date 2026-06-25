"""
run.py — backtest orchestrator.
Supports the legacy Phase 0 liquidation-fade flow and V3 event-driven flows.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .loader import cache_raw
from .features import compute_features, FeatureParams
from .engine import simulate, ExecParams
from .metrics import compute_metrics, save_summary
from .event_loader import build_event_windows, load_listing_events
from .event_engine import simulate_event_strategy
from .strategies import STRATEGIES


def load_universe(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("candidates", [])


def _inst_id_to_legacy_symbol(inst_id: str) -> str:
    normalized = inst_id.upper()
    for suffix in ["-USDT-SWAP", "-USDC-SWAP", "-SWAP"]:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)] + "USDT"
    return normalized.replace("-", "")


def load_strategy(name: str):
    strategy_cls = STRATEGIES.get(name)
    if strategy_cls is None:
        raise ValueError(f"Unknown strategy: {name}")
    return strategy_cls()


def run_event_strategy(
    start: date,
    end: date,
    events_path: str,
    out_dir: Path,
    strategy_name: str = "listing_fade",
    lookahead_minutes: int = 60,
) -> tuple[pd.DataFrame, dict[str, int]]:
    strategy = load_strategy(strategy_name)
    events = load_listing_events(events_path)
    if events.empty:
        raise ValueError(f"No events found in {events_path}")

    market_data_by_symbol: dict[str, pd.DataFrame] = {}
    symbols_needed = sorted({str(inst_id) for inst_id in events["inst_id"].dropna().unique()})

    for inst_id in symbols_needed:
        legacy_symbol = _inst_id_to_legacy_symbol(inst_id)
        raw_path = cache_raw(legacy_symbol, start, end)
        market_data = pd.read_parquet(raw_path)
        market_data_by_symbol[inst_id] = market_data

    event_windows = build_event_windows(
        market_data_by_symbol=market_data_by_symbol,
        events=events,
        lookback_minutes=0,
        lookahead_minutes=lookahead_minutes,
    )

    event_counts = {"events_total": len(events), "windows_built": len(event_windows), "signals": 0}
    all_signals: list[pd.DataFrame] = []

    for item in event_windows:
        event = item["event"]
        market_data = item["market_data"]
        signals = strategy.compute_signals(market_data, pd.DataFrame([event]))
        if not signals.empty:
            all_signals.append(signals)

    merged_signals = pd.concat(all_signals, ignore_index=True) if all_signals else pd.DataFrame()
    event_counts["signals"] = len(merged_signals)
    trades = simulate_event_strategy(merged_signals)
    trades.to_csv(out_dir / "event_trades.csv", index=False)
    return trades, event_counts


def _load_named_strategy_market_data(strategy_name: str, raw: pd.DataFrame) -> pd.DataFrame:
    if strategy_name == "beta_decouple":
        frame = pd.DataFrame(index=raw.index)
        frame["btc_close"] = raw["close"]
        frame["btc_return_60m"] = raw["close"].pct_change().fillna(0.0)
        realized_vol = raw["close"].pct_change().rolling(60, min_periods=5).std().fillna(0.0)
        frame["btc_rv_pct"] = realized_vol.rank(pct=True).fillna(0.0)
        frame["alt_close"] = raw["close"]
        frame["alt_vwap_60m"] = raw["close"].rolling(60, min_periods=5).mean().fillna(raw["close"])
        frame["alt_volume_24h"] = raw["quote_volume"].rolling(24 * 60, min_periods=5).sum().fillna(0.0)
        age_days = (pd.Series(frame.index, index=frame.index) - frame.index.min()).dt.total_seconds() / 86400.0
        frame["alt_age_days"] = age_days.clip(lower=0.0)
        return frame

    if strategy_name == "weekend_wick":
        frame = raw[["open", "high", "low", "close", "volume"]].copy()
        rolling_mean = frame["close"].rolling(24, min_periods=5).mean().fillna(frame["close"])
        rolling_std = frame["close"].rolling(24, min_periods=5).std(ddof=0).fillna(1.0)
        frame["wick_z"] = ((frame["close"] - rolling_mean) / rolling_std.replace(0, 1.0)).abs()
        return frame

    return raw


def run_named_strategy(
    strategy_name: str,
    start: date,
    end: date,
    universe_path: str | None,
    out_dir: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    strategy = load_strategy(strategy_name)
    strategy_config = getattr(strategy, "config", None)
    default_universe_fn = getattr(strategy_config, "universe_fn", lambda _=None: [])
    symbols = load_universe(universe_path) if universe_path else default_universe_fn(None)
    if not symbols:
        symbols = ["BTCUSDT"]

    all_signals: list[pd.DataFrame] = []
    for symbol in symbols:
        raw_path = cache_raw(symbol, start, end)
        raw = pd.read_parquet(raw_path)
        market_data = _load_named_strategy_market_data(strategy_name, raw)
        signals = strategy.compute_signals(market_data)
        if signals.empty:
            continue
        signals = signals.copy()
        signals["symbol"] = symbol
        all_signals.append(signals)

    merged_signals = pd.concat(all_signals, ignore_index=True) if all_signals else pd.DataFrame()
    if merged_signals.empty:
        trades = pd.DataFrame()
    elif bool(getattr(strategy_config, "is_event_driven", False)):
        trades = simulate_event_strategy(merged_signals)
    else:
        trades = merged_signals.copy()
        if "exit_ts" not in trades.columns and "valid_until_ts" in trades.columns:
            trades["exit_ts"] = trades["valid_until_ts"]
        if "exit_price" not in trades.columns:
            trades["exit_price"] = trades["target_price"]
        if "exit_reason" not in trades.columns:
            trades["exit_reason"] = "SIGNAL"
        trades["side"] = trades["signal"].map({1: "LONG", -1: "SHORT"})
        stop_distance_pct = (trades["entry_price"] - trades["stop_price"]).abs() / trades["entry_price"].replace(0, pd.NA)
        raw_ret = trades["signal"] * (trades["exit_price"] - trades["entry_price"]) / trades["entry_price"].replace(0, pd.NA)
        trades["pnl_R"] = raw_ret / stop_distance_pct.replace(0, pd.NA)
        trades["equity_after"] = 0.0

    if not trades.empty:
        trades.to_csv(out_dir / f"{strategy_name}_trades.csv", index=False)
    summary = {
        "strategy_name": strategy_name,
        "signals": len(merged_signals),
        "symbols": len(symbols),
    }
    return trades, summary


def run_symbol(symbol: str, start: date, end: date) -> tuple[pd.DataFrame, str]:
    """Run backtest for a single symbol. Returns (trades_df, liq_source)."""
    raw_path = cache_raw(symbol, start, end)
    raw = pd.read_parquet(raw_path)
    features_df = compute_features(raw)
    liq_source = features_df.attrs.get("liq_source", "UNKNOWN")

    # Drop warmup bars
    warmup = 24 * 60  # 24h
    features_df = features_df.iloc[warmup:]

    trades = simulate(features_df)
    trades["symbol"] = symbol
    return trades, liq_source


def sensitivity_scan(
    symbols: list[str],
    start: date,
    end: date,
    out_dir: Path,
) -> pd.DataFrame:
    """Grid search over 3 params (3x3x3 = 27 cells)."""
    from itertools import product

    liq_quantiles = [0.90, 0.95, 0.99]
    displacement_atr = [1.0, 1.5, 2.0]
    time_stops = [1, 2, 4]

    results = []
    for q, d, t in product(liq_quantiles, displacement_atr, time_stops):
        fparams = FeatureParams(
            liq_p_quantile=q,
            displacement_min_atr=d,
        )
        eparams = ExecParams(time_stop_bars=t)

        print(f"\n[SENSITIVITY] liq_q={q} displ={d} time_stop={t}", flush=True)
        all_trades = []
        for sym in symbols:
            try:
                raw_path = cache_raw(sym, start, end)
                raw = pd.read_parquet(raw_path)
                feats = compute_features(raw, fparams)
                feats = feats.iloc[24 * 60:]
                tr = simulate(feats, eparams)
                tr["symbol"] = sym
                all_trades.append(tr)
            except Exception as e:
                print(f"  skip {sym}: {e}", flush=True)

        if not all_trades:
            continue
        trades = pd.concat(all_trades, ignore_index=True)
        n_days = (end - start).days + 1
        m = compute_metrics(trades, len(symbols), n_days)

        # ROBUSTNESS per-cell decision (same gate)
        if m["win_rate"] >= 0.55 and m["ev_R"] >= 0.3 and m["profit_factor"] >= 1.4 \
           and m["trades_per_day_per_symbol"] >= 3 and m["max_consec_losses"] <= 6:
            cell_pass = True
        else:
            cell_pass = False

        results.append({
            "liq_p_quantile": q,
            "displacement_min_atr": d,
            "time_stop_bars": t,
            "n_trades": m["n_trades"],
            "win_rate": m["win_rate"],
            "ev_R": m["ev_R"],
            "profit_factor": m["profit_factor"],
            "tps": m["trades_per_day_per_symbol"],
            "max_consec_losses": m["max_consec_losses"],
            "pass": cell_pass,
        })

    grid = pd.DataFrame(results)
    out_dir.mkdir(parents=True, exist_ok=True)
    grid.to_csv(out_dir / "sensitivity_grid.csv", index=False)

    n_pass = grid["pass"].sum() if "pass" in grid.columns else 0
    n_total = len(grid)
    if n_pass >= 22:
        robustness = "HIGH"
    elif n_pass >= 14:
        robustness = "MEDIUM"
    elif n_pass >= 5:
        robustness = "LOW"
    else:
        robustness = "FAIL"

    print(f"\nROBUSTNESS: {robustness} ({n_pass}/{n_total} cells PASS)", flush=True)
    print(grid.to_string(index=False), flush=True)
    return grid


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--universe")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--out", required=True, help="output directory for reports/")
    p.add_argument("--sensitivity", action="store_true")
    p.add_argument("--mode", choices=["legacy", "event"], default="legacy")
    p.add_argument("--strategy")
    p.add_argument("--events")
    p.add_argument("--lookahead-minutes", type=int, default=60)
    args = p.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    n_days = (end - start).days + 1

    if args.mode == "event":
        if not args.events:
            print("ERROR: --events is required when --mode event")
            sys.exit(1)
        trades, event_counts = run_event_strategy(
            start=start,
            end=end,
            events_path=args.events,
            out_dir=out_dir,
            strategy_name=args.strategy or "listing_fade",
            lookahead_minutes=args.lookahead_minutes,
        )
        if trades.empty:
            print("ERROR: Event mode generated no trades")
            sys.exit(1)
        summary = compute_metrics(trades, max(event_counts["windows_built"], 1), n_days)
        save_summary(summary, out_dir / "summary.json")
        with open(out_dir / "event_counts.json", "w", encoding="utf-8") as f:
            json.dump(event_counts, f, ensure_ascii=True, indent=2)
        print(f"Event windows: {event_counts['windows_built']}")
        print(f"Signals: {event_counts['signals']}")
        print(f"Summary saved to {out_dir / 'summary.json'}")
        return

    if args.strategy and args.mode == "legacy":
        trades, strategy_summary = run_named_strategy(
            strategy_name=args.strategy,
            start=start,
            end=end,
            universe_path=args.universe,
            out_dir=out_dir,
        )
        if trades.empty:
            print(f"ERROR: Strategy mode generated no trades for {args.strategy}")
            sys.exit(1)
        metrics = compute_metrics(trades, max(strategy_summary["symbols"], 1), n_days)
        save_summary(metrics, out_dir / "summary.json")
        print(f"Strategy: {strategy_summary['strategy_name']}")
        print(f"Signals: {strategy_summary['signals']}")
        print(f"Summary saved to {out_dir / 'summary.json'}")
        return

    if not args.universe:
        print("ERROR: --universe is required when --mode legacy")
        sys.exit(1)

    all_symbols = load_universe(args.universe)

    # Read inventory, exclude bad symbols
    inventory_path = Path("data/raw/_inventory.json")
    excluded = set()
    if inventory_path.exists():
        with open(inventory_path, encoding="utf-8") as f:
            inv = json.load(f)
        for sym, info in inv.get("symbols", {}).items():
            if info.get("excluded", False):
                excluded.add(sym)

    symbols = [s for s in all_symbols if s not in excluded]
    if not symbols:
        print("ERROR: No valid symbols after inventory filter")
        sys.exit(1)

    print(f"Symbols: {len(symbols)} (excluded {len(excluded)}: {sorted(excluded)})")
    print(f"Date range: {start} ~ {end} ({n_days} days)")

    if args.sensitivity:
        # Sensitivity mode: runs all combos
        sensitivity_scan(symbols, start, end, out_dir)
        return

    t0 = time.time()
    all_trades = []
    liq_sources = set()

    for i, sym in enumerate(symbols):
        print(f"\n[{i+1}/{len(symbols)}] Processing {sym} ...", flush=True)
        try:
            trades, liq_src = run_symbol(sym, start, end)
            all_trades.append(trades)
            liq_sources.add(liq_src)
            print(f"  {sym}: {len(trades)} trades generated", flush=True)
        except Exception as e:
            print(f"  {sym}: FAILED - {e}", flush=True)

    if not all_trades:
        print("ERROR: No trades generated from any symbol")
        sys.exit(1)

    trades = pd.concat(all_trades, ignore_index=True)
    trades.to_csv(out_dir / "trades.csv", index=False)
    print(f"\nTotal trades: {len(trades)} saved to {out_dir / 'trades.csv'}")

    summary = compute_metrics(trades, len(symbols), n_days)
    save_summary(summary, out_dir / "summary.json")
    print(f"Summary saved to {out_dir / 'summary.json'}")

    elapsed = time.time() - t0
    liq_source_label = "REAL" if "REAL" in liq_sources else "OI_PROXY"

    print(f"\n{'='*60}")
    print(f"DECISION: {summary['decision']}")
    print(f"  Win Rate:          {summary['win_rate']:.2%}")
    print(f"  EV (R):            {summary['ev_R']:.4f}")
    print(f"  Profit Factor:     {summary['profit_factor']:.2f}")
    print(f"  Trades/day/symbol: {summary['trades_per_day_per_symbol']:.2f}")
    print(f"  Max Consc Losses:  {summary['max_consec_losses']}")
    print(f"  Max Drawdown:      {summary['max_drawdown_pct']:.1f}%")
    print(f"  N Trades:          {summary['n_trades']}")
    print(f"  Liq source:        {liq_source_label}")
    print(f"  Runtime:           {elapsed:.0f}s")
    print(f"{'='*60}")

    if summary["decision"] == "ABORT":
        sys.exit(2)
    elif summary["decision"] == "REPARAM":
        sys.exit(3)


if __name__ == "__main__":
    main()
