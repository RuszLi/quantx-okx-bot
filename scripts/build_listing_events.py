"""Build 6月 listing events JSON from OKX instruments.listTime.

Output: data/listing_events/okx_swap_listings_2025-06_to_2026-06.json
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OKX = "https://www.okx.com"
OUT_DIR = Path("data/listing_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def http_get(url: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "okx-bot/1.0", "Accept": "application/json"}, method="GET"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("Fetching instruments SWAP ...")
    url = OKX + "/api/v5/public/instruments?" + urllib.parse.urlencode({"instType": "SWAP"})
    payload = http_get(url)
    insts = payload.get("data") or []
    print(f"  total={len(insts)}")

    # Filter: listTime >= 2025-06-01 UTC (1748736000000)
    # We want all listings from 2025-06 through 2026-06-25
    cutoff_start = 1748736000000  # 2025-06-01 00:00 UTC
    cutoff_end = 1782422400000  # 2026-06-25 00:00 UTC (yesterday)

    events = []
    for inst in insts:
        lt = inst.get("listTime")
        if not lt:
            continue
        try:
            list_ts = int(lt)
        except Exception:
            continue
        if list_ts < cutoff_start or list_ts > cutoff_end:
            continue
        inst_id = inst.get("instId", "")
        state = inst.get("state", "")
        # Filter to USDT-settled (most liquid for $7 equity)
        settle = inst.get("settleCcy", "")
        if settle != "USDT":
            continue
        events.append({
            "inst_id": inst_id,
            "list_time_ms": list_ts,
            "list_time_iso": datetime.fromtimestamp(list_ts / 1000, tz=timezone.utc).isoformat(),
            "state": state,
            "settle_ccy": settle,
            "base_ccy": inst.get("baseCcy", ""),
            "quote_ccy": inst.get("quoteCcy", ""),
            "ct_val": float(inst.get("ctVal") or 0),
            "min_sz": float(inst.get("minSz") or 0),
            "tick_sz": float(inst.get("tickSz") or 0),
            "lever_max": float(inst.get("lever") or 0),
            "alias": inst.get("alias", ""),
            "category": inst.get("category", ""),
            "inst_family": inst.get("instFamily", ""),
        })

    # Sort by list_time_ms
    events.sort(key=lambda x: x["list_time_ms"])

    # Stats
    by_month: dict[str, int] = {}
    for e in events:
        dt = datetime.fromtimestamp(e["list_time_ms"] / 1000, tz=timezone.utc)
        ym = f"{dt.year}-{dt.month:02d}"
        by_month[ym] = by_month.get(ym, 0) + 1

    print(f"\nTotal listing events 2025-06 ~ 2026-06: {len(events)}")
    print("By month:")
    for ym in sorted(by_month.keys()):
        print(f"  {ym}: {by_month[ym]}")

    out_path = OUT_DIR / "okx_swap_listings_2025-06_to_2026-06.json"
    out_path.write_text(json.dumps({"events": events, "count": len(events)}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out_path}")

    # Also save a focused June 2026 listing events file for Strategy A
    june_events = [e for e in events if e["list_time_ms"] >= 1780416000000]  # 2026-06-01
    june_path = OUT_DIR / "okx_swap_listings_2026-06.json"
    june_path.write_text(json.dumps({"events": june_events, "count": len(june_events)}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"June 2026 listings: {len(june_events)} → {june_path}")

    # Print first 10 june events for sanity check
    print("\nFirst 10 June 2026 listings:")
    for e in june_events[:10]:
        print(f"  {e['inst_id']:25s}  list={e['list_time_iso'][:19]}  state={e['state']}  ct_val={e['ct_val']}  min_sz={e['min_sz']}")


if __name__ == "__main__":
    main()
