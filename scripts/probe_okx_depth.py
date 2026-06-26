"""Deep probe: announcements sample + instruments listTime distribution + Binance kline depth check."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OKX = "https://www.okx.com"


def http_get(url: str, timeout: float = 30.0) -> tuple[dict, int]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "okx-bot/1.0", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", errors="replace")), e.code
        except Exception:
            return {"_raw": ""}, e.code


def ts_ms_to_iso(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


# 1. Look at the single announcement we got back
print("=" * 70)
print(" announcements — inspect single returned record")
print("=" * 70)

url = (
    OKX + "/api/v5/support/announcements?"
    + urllib.parse.urlencode({"annType": "announcements-new-listings", "page": 1, "pageSize": 100})
)
payload, status = http_get(url)
data = payload.get("data") or []
print(f"HTTP {status}  count={len(data)}  code={payload.get('code')}  msg={payload.get('msg')}")
if data:
    print("\nFull single record:")
    print(json.dumps(data[0], indent=2, ensure_ascii=False, default=str)[:1500])

# Try alternative annType values to see if the endpoint actually returns historical
print("\n--- alt annType probes ---")
for alt in [
    "announcements-new-listings",
    "announcements",
    "announcements-new-crypto-listings",
    "announcements-delistings",
]:
    url = (
        OKX + "/api/v5/support/announcements?"
        + urllib.parse.urlencode({"annType": alt, "page": 1, "pageSize": 20})
    )
    payload, status = http_get(url)
    data = payload.get("data") or []
    print(f"  annType={alt!r}: HTTP {status} code={payload.get('code')} msg={payload.get('msg')} count={len(data)}")

# 2. Inspect instruments listTime to estimate how far back listing events can be reconstructed
print("\n" + "=" * 70)
print(" instruments SWAP — listTime distribution for listing events reconstruction")
print("=" * 70)

url = OKX + "/api/v5/public/instruments?" + urllib.parse.urlencode({"instType": "SWAP"})
payload, status = http_get(url)
data = payload.get("data") or []
print(f"HTTP {status}  count={len(data)}  code={payload.get('code')}")
if data:
    sample = data[0]
    print(f"\nSample fields: {sorted(sample.keys())}")
    print(f"Sample instId={sample.get('instId')}  listTime={sample.get('listTime')}  ({ts_ms_to_iso(sample.get('listTime'))})  state={sample.get('state')}  lever={sample.get('lever')}")

    list_times = []
    state_counts = {}
    for x in data:
        lt = x.get("listTime")
        if lt:
            try:
                list_times.append(int(lt))
            except Exception:
                pass
        s = x.get("state", "?")
        state_counts[s] = state_counts.get(s, 0) + 1
    print(f"\nState breakdown: {state_counts}")
    if list_times:
        list_times.sort()
        n = len(list_times)
        print(f"\nlistTime stats (n={n}):")
        print(f"  earliest: {ts_ms_to_iso(list_times[0])}")
        print(f"  latest:   {ts_ms_to_iso(list_times[-1])}")
        # Show distribution by year-month
        from collections import Counter
        ym = Counter()
        for ts in list_times:
            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            ym[f"{dt.year}-{dt.month:02d}"] += 1
        print("\nListings per year-month (top 20):")
        for k in sorted(ym.keys())[-20:]:
            print(f"  {k}: {ym[k]}")

# 3. Check Binance kline historical depth via data.binance.vision
print("\n" + "=" * 70)
print(" Binance public data — historical kline depth probe (no API key)")
print("=" * 70)

# Try fetching a daily kline file for BTCUSDT 6 months ago
import httpx
test_dates = ["2026-06-25", "2026-06-01", "2026-04-01", "2026-01-15", "2025-12-15", "2025-09-01"]
for d in test_dates:
    url = f"https://data.binance.vision/data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-{d}.zip"
    try:
        r = httpx.get(url, timeout=15.0, follow_redirects=True)
        size = len(r.content) if r.status_code == 200 else 0
        print(f"  {d}: HTTP {r.status_code}  size={size}B  url={url}")
    except Exception as e:
        print(f"  {d}: ERROR {type(e).__name__}: {e}")

# 4. OKX market/history-candles with bigger limit and longer pagination for BTC-USDT-SWAP
print("\n" + "=" * 70)
print(" OKX market/history-candles — test pagination depth (1m, max 100/page)")
print("=" * 70)

# Try larger pages and see if OKX allows > 100 per page
for test_limit in [100, 300, 900]:
    url = (
        OKX + "/api/v5/market/history-candles?"
        + urllib.parse.urlencode({"instId": "BTC-USDT-SWAP", "bar": "1m", "limit": test_limit})
    )
    payload, status = http_get(url)
    data = payload.get("data") or []
    print(f"  limit={test_limit}: HTTP {status} code={payload.get('code')} count={len(data)}")
    if data:
        print(f"    newest={ts_ms_to_iso(data[0][0])}  oldest={ts_ms_to_iso(data[-1][0])}")

# 5. OKX history-candles paginated as far as it goes
print("\n--- OKX history-candles deep pagination ---")
pages = 0
rows = 0
earliest = None
latest = None
after = None
while pages < 100:
    params = {"instId": "BTC-USDT-SWAP", "bar": "1m", "limit": 100}
    if after is not None:
        params["after"] = after
    url = OKX + "/api/v5/market/history-candles?" + urllib.parse.urlencode(params)
    payload, status = http_get(url)
    data = payload.get("data") or []
    if not data:
        print(f"  page {pages+1}: empty, stopping")
        break
    pages += 1
    rows += len(data)
    page_earliest = int(data[-1][0])
    page_latest = int(data[0][0])
    if earliest is None or page_earliest < earliest:
        earliest = page_earliest
    if latest is None or page_latest > latest:
        latest = page_latest
    after = page_earliest
    if pages % 20 == 0:
        print(f"  page {pages}: rows={rows}  earliest={ts_ms_to_iso(earliest)}  latest={ts_ms_to_iso(latest)}")
    time.sleep(0.1)

print(f"\nFinal: pages={pages} rows={rows}  earliest={ts_ms_to_iso(earliest)}  latest={ts_ms_to_iso(latest)} depth_days={(latest-earliest)/86400000:.2f}" if earliest and latest else "  no data")
