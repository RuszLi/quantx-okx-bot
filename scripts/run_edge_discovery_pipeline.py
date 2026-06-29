#!/usr/bin/env python3
"""run_edge_discovery_pipeline.py — V3.2 Automated Edge Discovery Pipeline.

Usage
-----
    # Dry-run: list candidates only (no backtesting)
    python scripts/run_edge_discovery_pipeline.py --families funding --mode grid --dry-run

    # Full pipeline: generate + backtest + validate + promote/graveyard
    python scripts/run_edge_discovery_pipeline.py --families funding,oi --mode random --n-samples 50

Arguments
---------
    --families   Comma-separated signal family names (default: "funding").
    --mode       Search mode: "grid" | "random" (default: "grid").
    --n-samples  Number of random samples (only for "random" mode; default: 10).
    --start      Training window start (default: 2024-01-01).
    --end        Training window end, exclusive (default: 2025-01-01).
    --dry-run    Only generate candidate list, skip backtesting & validation.
    --out-dir    Output directory (default: reports/pipeline_output/<run_id>/).

Notes
-----
    - The holdout window is fixed at 2025-01-01 onwards and CANNOT be
      overridden via CLI (see docs/plans/2026-06-28-1000-*.md §1.2).
    - Phase 1 (scaffold) & Phase 2 (data layer) are complete.
    - Phase 3-5 (generators, validator, promoter/graveyard) are under active
      development — in this build the pipeline runs in dry-run mode only
      and will raise NotImplementedError for full execution.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import argparse
import hashlib
import json
import shutil
import time
from datetime import datetime, timezone

import pandas as pd

REPORTS_ROOT = _PROJECT_ROOT / "reports" / "pipeline_output"


def _run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"run_{ts}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="V3.2 Automated Edge Discovery Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--families", default="funding", help="Comma-separated signal family names")
    parser.add_argument("--mode", default="grid", choices=["grid", "random"], help="Search mode")
    parser.add_argument("--n-samples", type=int, default=10, help="Random samples count")
    parser.add_argument("--start", default="2024-01-01", help="Training start")
    parser.add_argument("--end", default="2025-01-01", help="Training end (exclusive)")
    parser.add_argument("--dry-run", action="store_true", help="List candidates only")
    parser.add_argument("--out-dir", default=None, help="Output directory")
    return parser.parse_args()


def _get_generator(family: str):
    from src.pipeline.generators.funding_generator import FundingGenerator
    registry = {"funding": FundingGenerator()}
    gen = registry.get(family)
    if gen is None:
        from src.pipeline.families import FAMILY_REGISTRY
        if family in FAMILY_REGISTRY:
            raise NotImplementedError(f"Generator for family {family!r} not yet implemented.")
        raise ValueError(f"Unknown family {family!r}. Known: {list(registry)}")
    return gen


def stage_generate_candidates(families, mode, n_samples):
    from src.pipeline.search_space import ParameterSpace

    candidates = []
    for family in families:
        gen = _get_generator(family)
        ps = ParameterSpace(params=gen.default_search_space(), sampling=mode, random_samples=n_samples)
        param_iter = ps.iter_grid() if mode == "grid" else ps.iter_samples()

        for params in param_iter:
            ph = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
            candidates.append({
                "candidate_id": f"{family}_{ph}",
                "family": family,
                "params": params,
                "strategy_class": gen.__class__.__name__,
            })
    return candidates


def stage_write_candidates_csv(candidates, out_dir):
    pd.DataFrame(candidates).to_csv(out_dir / "candidates.csv", index=False)
    return out_dir / "candidates.csv"


def stage_dry_run_report(candidates, out_dir):
    from src.pipeline.families import FAMILY_REGISTRY

    lines = [
        "# Edge Discovery Pipeline — Dry-Run Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "| Family | Candidates | Signals | Generator |",
        "|--------|------------|---------|-----------|",
    ]
    family_counts = {}
    for c in candidates:
        family_counts[c["family"]] = family_counts.get(c["family"], 0) + 1
    for family, count in family_counts.items():
        sigs = ", ".join(FAMILY_REGISTRY[family].signals) if family in FAMILY_REGISTRY else "?"
        gen_name = _get_generator(family).__class__.__name__
        lines.append(f"| {family} | {count} | {sigs} | {gen_name} |")

    lines.extend(["", "## Sample Candidates", ""])
    for c in candidates[:5]:
        lines.append(f"- `{c['candidate_id']}` — family={c['family']}, params={c['params']}")
    if len(candidates) > 5:
        lines.append(f"- ... and {len(candidates) - 5} more")

    lines.extend([
        "",
        "## What Would Happen (Full Mode)",
        "",
        "1. **Executor**: run backtests for each candidate via run_named_strategy()",
        "2. **IS Gate**: filter with WR>=0.45, EV>=0.15R, PF>=1.3, max_consec_losses<=6",
        "3. **CPCV**: combinatorial purged cross-validation (n_groups=8, n_test_groups=2)",
        "4. **DSR**: deflated Sharpe ratio correction (p-value threshold 0.05)",
        "5. **WFA**: walk-forward analysis (enhancement evidence, not blocking)",
        "6. **Promoter/Graveyard**: PASS -> docs/strategies/<id>.md + registration;",
        "   ABORT/REPARAM -> docs/strategies/<id>.md (stage=rejected)",
        "",
        "> Dry-run mode: no backtests, no validation, no files modified outside --out-dir.",
    ])
    report = out_dir / "dry_run_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def _candidate_rows_to_objects(candidate_rows: list[dict[str, object]]):
    from src.pipeline.candidate import Candidate

    return [
        Candidate(
            candidate_id=str(row["candidate_id"]),
            family=str(row["family"]),
            params=dict(row.get("params", {})),
            strategy_class=str(row.get("strategy_class", "")),
        )
        for row in candidate_rows
    ]


def _load_market_bundle(family: str, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, pd.DataFrame]:
    from src.pipeline.data_layer import get_funding, get_klines

    if family != "funding":
        raise NotImplementedError(f"Full execution for family {family!r} is not implemented yet.")
    market = get_klines("BTCUSDT", "1h", start, end)
    funding = get_funding("BTC-USDT-SWAP", start, end)
    if market.empty:
        raise ValueError("No market data available for funding family in requested training window.")
    bundle = market.copy()
    if not funding.empty and "funding_rate" in funding.columns:
        bundle = bundle.join(funding[["funding_rate"]], how="left")
        bundle["funding_rate"] = bundle["funding_rate"].ffill().fillna(0.0)
    else:
        bundle["funding_rate"] = 0.0
    return {"market_data": bundle}


def run_full_pipeline(candidates, start: str, end: str, out_dir: Path):
    from src.pipeline.executor import Executor
    from src.pipeline.generators.funding_generator import FundingGenerator
    from src.pipeline.graveyard import Graveyard
    from src.pipeline.promoter import Promoter
    from src.pipeline.protocol import HOLDOUT_WINDOW_START
    from src.pipeline.validator import evaluate

    training_start = pd.Timestamp(start, tz="UTC")
    training_end = pd.Timestamp(end, tz="UTC")
    holdout_start = max(pd.Timestamp(HOLDOUT_WINDOW_START, tz="UTC"), training_end)
    holdout_end = pd.Timestamp(datetime.now(timezone.utc))

    promoted_dir = out_dir / "promoted"
    rejected_dir = out_dir / "rejected"
    promoted_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    candidate_objects = _candidate_rows_to_objects(candidates)
    family_registry = {"funding": FundingGenerator()}
    executor = Executor(family_registry)
    promoter = Promoter(project_root=_PROJECT_ROOT)
    graveyard = Graveyard()

    family_bundles: dict[str, dict[str, pd.DataFrame]] = {}
    holdout_bundles: dict[str, dict[str, pd.DataFrame]] = {}
    results_rows: list[dict[str, object]] = []

    for candidate in candidate_objects:
        strategy_class = family_registry[candidate.family].generate(candidate.params)
        bundle = family_bundles.get(candidate.family)
        if bundle is None:
            bundle = _load_market_bundle(candidate.family, training_start, training_end)
            family_bundles[candidate.family] = bundle
        run_result = executor.run_candidate(candidate, bundle)

        holdout_returns = None
        if holdout_end > holdout_start:
            holdout_bundle = holdout_bundles.get(candidate.family)
            if holdout_bundle is None:
                holdout_bundle = _load_market_bundle(candidate.family, holdout_start, holdout_end)
                holdout_bundles[candidate.family] = holdout_bundle
            holdout_result = executor.run_candidate(candidate, holdout_bundle)
            holdout_returns = holdout_result["trades_df"].get("pnl_R", pd.Series(dtype="float64"))

        validation = evaluate(
            candidate,
            run_result["trades_df"],
            run_result["summary"],
            run_result["robustness"],
            holdout_returns=holdout_returns,
        )
        strategy_doc_path: str | None = None
        if validation["verdict"] == "PASS":
            promoter.register_strategy(strategy_class, strategy_class.config, candidate.candidate_id)
            strategy_doc_path = str((_PROJECT_ROOT / "docs" / "strategies" / f"{candidate.candidate_id}.md"))
            shutil.copy2(strategy_doc_path, promoted_dir / Path(strategy_doc_path).name)
        else:
            strategy_doc_path = graveyard.bury(
                candidate.candidate_id,
                candidate.family,
                candidate.params,
                {**run_result["summary"], **validation["gate_results"]},
                list(validation["reasons"]),
                strategy_name=strategy_class.config.name,
                bar_freq=strategy_class.config.bar_freq,
                is_event_driven=strategy_class.config.is_event_driven,
                leverage_cap=float(strategy_class.config.leverage_cap),
                risk_per_trade_r=float(strategy_class.config.risk_per_trade_R),
            )
            shutil.copy2(strategy_doc_path, rejected_dir / Path(strategy_doc_path).name)

        results_rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "family": candidate.family,
                "verdict": validation["verdict"],
                "robustness": run_result["robustness"],
                "n_trades": run_result["summary"].get("n_trades", 0),
                "ev_R": run_result["summary"].get("ev_R", 0.0),
                "strategy_doc_path": strategy_doc_path,
                "reasons": " | ".join(validation["reasons"]),
            }
        )

    results_path = out_dir / "results.csv"
    pd.DataFrame(results_rows).to_csv(results_path, index=False)
    return results_path


def main():
    args = _parse_args()
    families = [f.strip().lower() for f in args.families.split(",")]
    run_id = _run_id()
    out_dir = Path(args.out_dir) if args.out_dir else REPORTS_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{run_id}] Starting edge discovery pipeline")
    print(f"  Families: {', '.join(families)}")
    print(f"  Mode: {args.mode}")
    print(f"  Dry-run: {args.dry_run}")
    print(f"  Output: {out_dir}")
    print()

    print("[1/4] Generating candidates...")
    t0 = time.time()
    candidates = stage_generate_candidates(families, args.mode, args.n_samples)
    print(f"  -> {len(candidates)} candidates in {time.time() - t0:.1f}s")
    print()

    print("[2/4] Writing candidates.csv...")
    csv_path = stage_write_candidates_csv(candidates, out_dir)
    print(f"  -> {csv_path}")
    print()

    if args.dry_run:
        print("[3/4] Generating dry-run report...")
        report_path = stage_dry_run_report(candidates, out_dir)
        print(f"  -> {report_path}")
    else:
        print("[3/4] Running full pipeline...")
        results_path = run_full_pipeline(candidates, args.start, args.end, out_dir)
        print(f"  -> {results_path}")

    print(f"[4/4] Pipeline complete. Output: {out_dir}")


if __name__ == "__main__":
    main()
