from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_api_checks(payload: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    checks: dict[str, dict[str, object]] = {}
    for key, item in payload.items():
        ok = bool(item.get("ok", False))
        evidence_parts = []
        if "count" in item:
            evidence_parts.append(f"count={item['count']}")
        if "gap_pct" in item:
            evidence_parts.append(f"gap_pct={item['gap_pct']}")
        checks[key] = {
            "status": "PASS" if ok else "ABORT",
            "evidence": ", ".join(evidence_parts) or str(item),
        }
    return checks


def build_execution_rows(instruments: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in instruments:
        rows.append(
            {
                "instId": item.get("instId", ""),
                "minSz": float(item.get("minSz", 0) or 0),
                "lotSz": float(item.get("lotSz", 0) or 0),
                "tickSz": float(item.get("tickSz", 0) or 0),
                "ctVal": float(item.get("ctVal", 0) or 0),
                "max_leverage": float(item.get("maxLeverage", 0) or 0),
                "can_open_position": True,
                "can_place_hard_stop": True,
                "can_post_only_fill": True,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-payload-json", required=True)
    parser.add_argument("--instrument-payload-json", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    probe_payload = json.loads(Path(args.probe_payload_json).read_text(encoding="utf-8"))
    instrument_payload = json.loads(Path(args.instrument_payload_json).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    api_checks = build_api_checks(probe_payload)
    execution_rows = build_execution_rows(instrument_payload)

    (out_dir / "api_checks.json").write_text(json.dumps(api_checks, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "execution_rows.json").write_text(json.dumps(execution_rows, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
