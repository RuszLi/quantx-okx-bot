from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from src.data.okx_announcements import fetch_announcements
from src.data.okx_funding import fetch_funding_history
from src.data.okx_oi import fetch_open_interest
from src.okx_sdk import market_api, public_api


def fetch_public_instruments(inst_type: str = "SWAP") -> list[dict[str, object]]:
    client = public_api()
    result = client.get_instruments(instType=inst_type)
    return list(result.get("data") or [])


def fetch_public_candles(inst_id: str, limit: int = 10) -> pd.DataFrame:
    client = market_api()
    result = client.get_candlesticks(instId=inst_id, bar="1m", limit=str(limit))
    rows = result.get("data") or []
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"])
    for column in ["open", "high", "low", "close", "vol", "volCcy", "volCcyQuote"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["ts"] = pd.to_datetime(pd.to_numeric(frame["ts"], errors="coerce"), unit="ms", utc=True, errors="coerce")
    return frame.sort_values("ts").reset_index(drop=True)


def _default_fetch_candles(inst_id: str, limit: int = 10) -> pd.DataFrame:
    return fetch_public_candles(inst_id, limit=limit)


def build_probe_payload(
    instruments: list[dict[str, object]],
    announcements: list[dict[str, object]],
    candles: pd.DataFrame,
    funding: pd.DataFrame,
    oi: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    return {
        "instruments": {"ok": len(instruments) > 0, "count": len(instruments)},
        "announcements": {"ok": len(announcements) > 0, "count": len(announcements)},
        "candles": {"ok": not candles.empty, "gap_pct": 0.0 if not candles.empty else 1.0},
        "funding": {"ok": not funding.empty, "count": len(funding)},
        "oi": {"ok": not oi.empty, "count": len(oi)},
    }


def run_public_probe(
    inst_id: str,
    candle_fetcher: Callable[[str, int], pd.DataFrame] | None = None,
) -> dict[str, object]:
    candle_fetcher = candle_fetcher or _default_fetch_candles
    try:
        instruments = fetch_public_instruments("SWAP")
    except Exception:
        instruments = []

    announcements = [item.raw for item in fetch_announcements(page_size=5)]
    candles = candle_fetcher(inst_id, 10)
    funding = fetch_funding_history(inst_id, limit=10)
    oi = fetch_open_interest(inst_id, limit=10)
    return build_probe_payload(instruments, announcements, candles, funding, oi)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inst-id", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    payload = run_public_probe(args.inst_id)
    instruments = fetch_public_instruments("SWAP")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "probe_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "instrument_payload.json").write_text(json.dumps(instruments, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
