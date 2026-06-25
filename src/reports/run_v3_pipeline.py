from __future__ import annotations

import argparse
from pathlib import Path

from src.backtest.batch_runner import run_batch_strategies
from src.reports.build_pipeline import run_v3_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy-names", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--universe-path")
    parser.add_argument("--backtests-dir", required=True)
    parser.add_argument("--probe-payload-json", required=True)
    parser.add_argument("--instrument-payload-json", required=True)
    parser.add_argument("--probe-out-dir", required=True)
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--skip-batch-run", action="store_true")
    args = parser.parse_args()

    strategy_names = [name.strip() for name in args.strategy_names.split(",") if name.strip()]
    run_v3_pipeline(
        strategy_names=strategy_names,
        start=args.start,
        end=args.end,
        universe_path=args.universe_path,
        backtests_dir=Path(args.backtests_dir),
        probe_payload_json=Path(args.probe_payload_json),
        instrument_payload_json=Path(args.instrument_payload_json),
        probe_out_dir=Path(args.probe_out_dir),
        reports_dir=Path(args.reports_dir),
        slippage_bps=args.slippage_bps,
        skip_batch_run=args.skip_batch_run,
    )


if __name__ == "__main__":
    main()
