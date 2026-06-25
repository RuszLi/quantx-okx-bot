from __future__ import annotations

from pathlib import Path


def write_api_signoff_report(checks: dict[str, dict[str, object]], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# V3 API Signoff", "", "## Checks", ""]
    for dataset, payload in checks.items():
        lines.append(f"- {dataset}: {payload.get('status', 'UNKNOWN')} | {payload.get('evidence', '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_execution_feasibility_report(rows: list[dict[str, object]], out_path: str | Path) -> Path:
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# V3 Execution Feasibility",
        "",
        "| instId | minSz | lotSz | tickSz | ctVal | can_open_position | can_place_hard_stop | can_post_only_fill |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('instId', '')} | {row.get('minSz', '')} | {row.get('lotSz', '')} | {row.get('tickSz', '')} | {row.get('ctVal', '')} | {row.get('can_open_position', '')} | {row.get('can_place_hard_stop', '')} | {row.get('can_post_only_fill', '')} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
