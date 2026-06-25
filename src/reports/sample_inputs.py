from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.reports.collect_inputs import collect_report_inputs


def sample_report_inputs(backtests_dir: str | Path, api_checks_json: str | Path, execution_rows_json: str | Path) -> dict[str, object]:
    api_checks = json.loads(Path(api_checks_json).read_text(encoding="utf-8"))
    execution_rows = json.loads(Path(execution_rows_json).read_text(encoding="utf-8"))
    return collect_report_inputs(backtests_dir=backtests_dir, api_checks=api_checks, execution_rows=execution_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtests-dir", required=True)
    parser.add_argument("--api-checks-json", required=True)
    parser.add_argument("--execution-rows-json", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    inputs = sample_report_inputs(args.backtests_dir, args.api_checks_json, args.execution_rows_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "strategy_metrics.json").write_text(json.dumps(inputs["strategy_metrics"], indent=2, ensure_ascii=False), encoding="utf-8")
    inputs["combo_summary"].to_csv(out_dir / "combo_summary.csv", index=False)
    inputs["paper_trades"].to_csv(out_dir / "paper_trades.csv", index=False)
    (out_dir / "api_checks.json").write_text(json.dumps(inputs["api_checks"], indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "execution_rows.json").write_text(json.dumps(inputs["execution_rows"], indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
