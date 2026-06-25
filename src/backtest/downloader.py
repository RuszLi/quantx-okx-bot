"""
Binance Futures (USDⓈ-M) public data downloader for Phase 0 backtest.

Sources (data.binance.vision):
  - klines/{SYMBOL}/1m/...               1-minute klines (price + volume)
  - metrics/{SYMBOL}/...                  5-minute OI + taker buy/sell + long/short ratio
  - liquidationSnapshot/{SYMBOL}/...      raw liquidation events (may be deprecated; we try and fall back)

Layout on disk:
  data/raw/{kind}/{SYMBOL}/{SYMBOL}-{kind}-{YYYY-MM-DD}.zip

Designed to be idempotent: existing non-empty files are skipped.
Proxy honored via env (HTTP_PROXY / ALL_PROXY) or default 127.0.0.1:7890.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE = "https://data.binance.vision/data/futures/um/daily"
PROXY = os.getenv("HTTP_PROXY") or os.getenv("ALL_PROXY") or "http://127.0.0.1:7890"
DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw"

KINDS: dict[str, callable] = {
    "klines_1m":           lambda s, d: f"{BASE}/klines/{s}/1m/{s}-1m-{d.isoformat()}.zip",
    "metrics":             lambda s, d: f"{BASE}/metrics/{s}/{s}-metrics-{d.isoformat()}.zip",
    "liquidationSnapshot": lambda s, d: f"{BASE}/liquidationSnapshot/{s}/{s}-liquidationSnapshot-{d.isoformat()}.zip",
}


def target_path(kind: str, symbol: str, d: date) -> Path:
    return DATA_ROOT / kind / symbol / f"{symbol}-{kind}-{d.isoformat()}.zip"


async def fetch(client: httpx.AsyncClient, kind: str, symbol: str, d: date) -> tuple[str, str]:
    out = target_path(kind, symbol, d)
    if out.exists() and out.stat().st_size > 0:
        return ("cached", str(out))
    url = KINDS[kind](symbol, d)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = await client.get(url, timeout=60.0)
        if r.status_code == 404:
            return ("404", url)
        r.raise_for_status()
        out.write_bytes(r.content)
        return ("ok", str(out))
    except httpx.HTTPError as e:
        return ("err", f"{url} :: {type(e).__name__}: {e}")


async def run(symbols: list[str], start: date, end: date, kinds: list[str], concurrency: int) -> dict:
    sem = asyncio.Semaphore(concurrency)
    tally: dict[str, int] = {"ok": 0, "cached": 0, "404": 0, "err": 0}
    err_samples: list[str] = []

    proxy_kw = {"proxy": PROXY} if PROXY else {}
    async with httpx.AsyncClient(http2=False, **proxy_kw) as client:
        async def task(kind: str, sym: str, d: date) -> None:
            async with sem:
                status, msg = await fetch(client, kind, sym, d)
                tally[status] = tally.get(status, 0) + 1
                if status == "ok":
                    print(f"  ok    {sym:10s} {kind:22s} {d}", flush=True)
                elif status == "404" and len(err_samples) < 10:
                    err_samples.append(f"404 {kind} {sym} {d}")
                elif status == "err" and len(err_samples) < 10:
                    err_samples.append(msg)

        jobs = []
        d = start
        while d <= end:
            for sym in symbols:
                for kind in kinds:
                    jobs.append(task(kind, sym, d))
            d += timedelta(days=1)
        await asyncio.gather(*jobs)

    return {"counts": tally, "err_samples": err_samples}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Binance public data downloader")
    p.add_argument("--symbols", nargs="+", required=True, help="e.g. SOLUSDT DOGEUSDT")
    p.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--end", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--kinds", nargs="+", default=list(KINDS.keys()), choices=list(KINDS.keys()))
    p.add_argument("--concurrency", type=int, default=8)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    print(f"proxy={PROXY!r}  root={DATA_ROOT}", file=sys.stderr)
    res = asyncio.run(run(args.symbols, start, end, args.kinds, args.concurrency))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
