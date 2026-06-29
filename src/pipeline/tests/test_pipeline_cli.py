from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pandas as pd

import scripts.run_edge_discovery_pipeline as pipeline_cli


def test_full_pipeline_main_writes_results_and_rejected_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        pipeline_cli,
        "_parse_args",
        lambda: Namespace(
            families="funding",
            mode="random",
            n_samples=1,
            start="2024-01-01",
            end="2025-01-01",
            dry_run=False,
            out_dir=str(tmp_path),
        ),
    )
    monkeypatch.setattr(pipeline_cli, "_run_id", lambda: "run_test")
    monkeypatch.setattr(
        pipeline_cli,
        "stage_generate_candidates",
        lambda families, mode, n_samples: [
            {
                "candidate_id": "funding_case_01",
                "family": "funding",
                "params": {"z_score_threshold": 2.0},
                "strategy_class": "FundingGenerator",
            }
        ],
    )

    def _fake_full_pipeline(candidates, start, end, out_dir):
        _ = candidates, start, end
        promoted_dir = out_dir / "promoted"
        rejected_dir = out_dir / "rejected"
        promoted_dir.mkdir(parents=True, exist_ok=True)
        rejected_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "candidate_id": "funding_case_01",
                    "family": "funding",
                    "verdict": "ABORT",
                    "strategy_doc_path": str(rejected_dir / "funding_case_01.md"),
                }
            ]
        ).to_csv(out_dir / "results.csv", index=False)
        (rejected_dir / "funding_case_01.md").write_text("# rejected", encoding="utf-8")
        return out_dir / "results.csv"

    monkeypatch.setattr(
        pipeline_cli,
        "run_full_pipeline",
        _fake_full_pipeline,
        raising=False,
    )

    pipeline_cli.main()

    assert (tmp_path / "candidates.csv").exists()
    assert (tmp_path / "results.csv").exists()
    assert (tmp_path / "rejected" / "funding_case_01.md").exists()
