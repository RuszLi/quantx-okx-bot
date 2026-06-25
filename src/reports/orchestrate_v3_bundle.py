from __future__ import annotations

import argparse
from pathlib import Path

from src.reports.workflow import build_report_bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtests-dir", required=True)
    parser.add_argument("--api-checks-json", required=True)
    parser.add_argument("--execution-rows-json", required=True)
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    args = parser.parse_args()

    build_report_bundle(
        backtests_dir=Path(args.backtests_dir),
        reports_dir=Path(args.reports_dir),
        api_checks_json=Path(args.api_checks_json),
        execution_rows_json=Path(args.execution_rows_json),
        slippage_bps=args.slippage_bps,
    )


if __name__ == "__main__":
    main()
