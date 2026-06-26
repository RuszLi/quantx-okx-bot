"""Probe OKX public endpoints to gather real API signoff evidence for §18.2."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OKX = "https://www.okx.com"
OUT_DIR = Path("reports/v3_output/_probe")


def http_get(path: str, params: dict | None = None, timeout: float = 30.0) -> tuple[dict, float, str, int]:
    q = urllib.parse.urlencode(params or {})
    url = OKX + path + ("?" + q if q else "")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "okx-bot/1.0", "Accept": "application/json"},
        method="GET",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        status = e.code
    elapsed = time.time() - t0
    try:
        return json.loads(body), elapsed, url, status
    except json.JSONDecodeError:
        return {"_raw": body, "code": "PARSE_ERR"}, elapsed, url, status


def ts_ms_to_iso(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def probe_instruments() -> dict:
    payload, dt, url, status = http_get("/api/v5/public/instruments", {"instType": "SWAP"})
    data = payload.get("data") or []
    out = {
        "endpoint": "/api/v5/public/instruments",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
    }
    if data:
        sample = data[0]
        out["sample_fields"] = sorted(sample.keys())
        out["sample"] = {k: sample.get(k) for k in ["instId", "instType", "state", "settleCcy", "ctVal", "ctValCcy", "lotSz", "minSz", "tickSz", "lever", "listTime", "listTimeStr"]}
        out["sample_listTime_iso"] = ts_ms_to_iso(sample.get("listTime"))
        list_times = [int(x.get("listTime") or 0) for x in data if x.get("listTime")]
        if list_times:
            out["earliest_listTime_iso"] = ts_ms_to_iso(min(list_times))
            out["latest_listTime_iso"] = ts_ms_to_iso(max(list_times))
        states = {}
        for x in data:
            s = x.get("state", "?")
            states[s] = states.get(s, 0) + 1
        out["state_breakdown"] = states
    return out


def probe_announcements() -> dict:
    payload, dt, url, status = http_get(
        "/api/v5/support/announcements",
        {"annType": "announcements-new-listings", "page": 1, "pageSize": 100},
    )
    data = payload.get("data") or []
    out = {
        "endpoint": "/api/v5/support/announcements",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
    }
    if data:
        sample = data[0]
        out["sample_fields"] = sorted(sample.keys())
        out["sample"] = {k: sample.get(k) for k in ["announcementId", "title", "publishedAt", "publishedAtStr", "type", "subType", "url"]}
        out["sample_publishedAt_iso"] = ts_ms_to_iso(sample.get("publishedAt"))
        pub_times = [int(x.get("publishedAt") or 0) for x in data if x.get("publishedAt")]
        if pub_times:
            out["earliest_publishedAt_iso"] = ts_ms_to_iso(min(pub_times))
            out["latest_publishedAt_iso"] = ts_ms_to_iso(max(pub_times))
        out["sample_titles_first_5"] = [x.get("title", "")[:140] for x in data[:5]]
    return out


def probe_announcements_paginated(max_pages: int = 10) -> dict:
    """Try to fetch up to max_pages pages to estimate historical depth."""
    all_count = 0
    earliest = None
    latest = None
    page = 1
    while page <= max_pages:
        payload, dt, url, status = http_get(
            "/api/v5/support/announcements",
            {"annType": "announcements-new-listings", "page": page, "pageSize": 100},
        )
        data = payload.get("data") or []
        if not data:
            break
        all_count += len(data)
        for x in data:
            pt = x.get("publishedAt")
            if pt:
                t = int(pt)
                if earliest is None or t < earliest:
                    earliest = t
                if latest is None or t > latest:
                    latest = t
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.2)
    return {
        "pages_fetched": page - 1 if page <= max_pages else max_pages,
        "total_count": all_count,
        "earliest_publishedAt_iso": ts_ms_to_iso(earliest) if earliest else None,
        "latest_publishedAt_iso": ts_ms_to_iso(latest) if latest else None,
    }


def probe_candles(inst_id: str = "BTC-USDT-SWAP") -> dict:
    payload, dt, url, status = http_get(
        "/api/v5/market/candles",
        {"instId": inst_id, "bar": "1m", "limit": 300},
    )
    data = payload.get("data") or []
    out = {
        "endpoint": "/api/v5/market/candles",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
        "inst_id": inst_id,
    }
    if data:
        out["sample_newest"] = data[0]
        out["sample_oldest"] = data[-1]
        out["newest_ts_iso"] = ts_ms_to_iso(data[0][0])
        out["oldest_ts_iso"] = ts_ms_to_iso(data[-1][0])
        out["window_hours"] = round((int(data[0][0]) - int(data[-1][0])) / 3600000, 2)
    return out


def probe_candles_history(inst_id: str = "BTC-USDT-SWAP", target_days: int = 180) -> dict:
    """Paginate backwards via 'after' to estimate how deep 1m history goes."""
    pages = 0
    rows = 0
    earliest_ts = None
    latest_ts = None
    after = None
    while pages < 50:
        params = {"instId": inst_id, "bar": "1m", "limit": 100}
        if after is not None:
            params["after"] = after
        payload, dt, url, status = http_get("/api/v5/market/history-candles", params)
        data = payload.get("data") or []
        if not data:
            break
        pages += 1
        rows += len(data)
        page_earliest = int(data[-1][0])
        page_latest = int(data[0][0])
        if earliest_ts is None or page_earliest < earliest_ts:
            earliest_ts = page_earliest
        if latest_ts is None or page_latest > latest_ts:
            latest_ts = page_latest
        # next page: before page_earliest
        after = page_earliest
        # break if we've gone back far enough
        if target_days > 0:
            target_ms = latest_ts - target_days * 86400 * 1000
            if page_earliest <= target_ms:
                break
        time.sleep(0.15)
    return {
        "endpoint": "/api/v5/market/history-candles",
        "inst_id": inst_id,
        "pages_fetched": pages,
        "rows_fetched": rows,
        "earliest_ts_iso": ts_ms_to_iso(earliest_ts),
        "latest_ts_iso": ts_ms_to_iso(latest_ts),
        "history_depth_days": round((latest_ts - earliest_ts) / 86400000, 2) if earliest_ts and latest_ts else None,
    }


def probe_funding(inst_id: str = "BTC-USDT-SWAP") -> dict:
    payload, dt, url, status = http_get(
        "/api/v5/public/funding-rate-history",
        {"instId": inst_id, "limit": 100},
    )
    data = payload.get("data") or []
    out = {
        "endpoint": "/api/v5/public/funding-rate-history",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
        "inst_id": inst_id,
    }
    if data:
        out["sample_fields"] = sorted(data[0].keys())
        out["newest"] = data[0]
        out["oldest"] = data[-1]
        out["newest_funding_time_iso"] = ts_ms_to_iso(data[0].get("fundingTime"))
        out["oldest_funding_time_iso"] = ts_ms_to_iso(data[-1].get("fundingTime"))
    return out


def probe_funding_deep(inst_id: str = "BTC-USDT-SWAP", max_pages: int = 10) -> dict:
    """Paginate funding-rate-history via 'after' to estimate depth."""
    pages = 0
    rows = 0
    earliest = None
    latest = None
    after = None
    while pages < max_pages:
        params = {"instId": inst_id, "limit": 100}
        if after is not None:
            params["after"] = after
        payload, dt, url, status = http_get("/api/v5/public/funding-rate-history", params)
        data = payload.get("data") or []
        if not data:
            break
        pages += 1
        rows += len(data)
        for x in data:
            ft = x.get("fundingTime")
            if ft:
                t = int(ft)
                if earliest is None or t < earliest:
                    earliest = t
                if latest is None or t > latest:
                    latest = t
        # next page: before oldest in this batch
        oldest_ft = min(int(x.get("fundingTime") or 0) for x in data)
        if oldest_ft == 0:
            break
        after = oldest_ft
        time.sleep(0.15)
    return {
        "endpoint": "/api/v5/public/funding-rate-history",
        "inst_id": inst_id,
        "pages_fetched": pages,
        "rows_fetched": rows,
        "earliest_funding_time_iso": ts_ms_to_iso(earliest),
        "latest_funding_time_iso": ts_ms_to_iso(latest),
        "history_depth_days": round((latest - earliest) / 86400000, 2) if earliest and latest else None,
    }


def probe_oi(inst_id: str = "BTC-USDT-SWAP") -> dict:
    payload, dt, url, status = http_get(
        "/api/v5/rubik/stat/contracts/open-interest-history",
        {"instId": inst_id, "period": "1H", "limit": 100},
    )
    data = payload.get("data") or []
    out = {
        "endpoint": "/api/v5/rubik/stat/contracts/open-interest-history",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
        "inst_id": inst_id,
    }
    if data:
        out["sample_newest"] = data[0]
        out["sample_oldest"] = data[-1]
        try:
            out["newest_ts_iso"] = ts_ms_to_iso(int(data[0][0]))
            out["oldest_ts_iso"] = ts_ms_to_iso(int(data[-1][0]))
            out["history_depth_days"] = round((int(data[0][0]) - int(data[-1][0])) / 86400000, 2)
        except Exception:
            pass
    return out


def probe_oi_alt_period(inst_id: str = "BTC-USDT-SWAP") -> dict:
    """Try shorter period (5m) to check granularity availability."""
    out = {}
    for period in ["5m", "1H", "1D"]:
        payload, dt, url, status = http_get(
            "/api/v5/rubik/stat/contracts/open-interest-history",
            {"instId": inst_id, "period": period, "limit": 10},
        )
        data = payload.get("data") or []
        out[period] = {
            "url": url,
            "http_status": status,
            "code": payload.get("code"),
            "msg": payload.get("msg"),
            "count": len(data),
            "sample_newest": data[0] if data else None,
            "sample_oldest": data[-1] if data else None,
        }
    return out


def probe_funding_rate(inst_id: str = "BTC-USDT-SWAP") -> dict:
    """Live (current) funding rate — point-in-time field."""
    payload, dt, url, status = http_get(
        "/api/v5/public/funding-rate",
        {"instId": inst_id},
    )
    data = payload.get("data") or []
    return {
        "endpoint": "/api/v5/public/funding-rate",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
        "sample": data[0] if data else None,
    }


def probe_mark_price(inst_id: str = "BTC-USDT-SWAP") -> dict:
    payload, dt, url, status = http_get(
        "/api/v5/public/mark-price",
        {"instId": inst_id},
    )
    data = payload.get("data") or []
    return {
        "endpoint": "/api/v5/public/mark-price",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
        "sample": data[0] if data else None,
    }


def probe_ticker(inst_id: str = "BTC-USDT-SWAP") -> dict:
    payload, dt, url, status = http_get(
        "/api/v5/market/ticker",
        {"instId": inst_id},
    )
    data = payload.get("data") or []
    return {
        "endpoint": "/api/v5/market/ticker",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
        "sample": data[0] if data else None,
    }


def probe_books(inst_id: str = "BTC-USDT-SWAP") -> dict:
    """Order book snapshot — for spread / post-only feasibility evidence."""
    payload, dt, url, status = http_get(
        "/api/v5/market/books",
        {"instId": inst_id, "sz": 5},
    )
    data = payload.get("data") or []
    out = {
        "endpoint": "/api/v5/market/books",
        "url": url,
        "http_status": status,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "elapsed_sec": round(dt, 3),
        "count": len(data),
    }
    if data:
        sample = data[0]
        out["sample_fields"] = sorted(sample.keys())
        out["asks_first"] = sample.get("asks", [])[:3]
        out["bids_first"] = sample.get("bids", [])[:3]
        try:
            best_ask = float(sample["asks"][0][0])
            best_bid = float(sample["bids"][0][0])
            mid = (best_ask + best_bid) / 2
            out["best_ask"] = best_ask
            out["best_bid"] = best_bid
            out["mid"] = mid
            out["spread_bps"] = round((best_ask - best_bid) / mid * 10000, 2) if mid else None
        except Exception:
            pass
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 70)
    print("OKX public API probe — for V3 §18.2 signoff")
    print("=" * 70)

    print("\n[1/9] instruments SWAP ...")
    r1 = probe_instruments()
    print(f"  count={r1['count']} code={r1['code']} elapsed={r1['elapsed_sec']}s")

    print("\n[2/9] announcements page=1 ...")
    r2 = probe_announcements()
    print(f"  count={r2['count']} code={r2['code']} elapsed={r2['elapsed_sec']}s")
    print(f"  earliest={r2.get('earliest_publishedAt_iso')}  latest={r2.get('latest_publishedAt_iso')}")

    print("\n[3/9] announcements paginated (up to 10 pages) ...")
    r3 = probe_announcements_paginated(max_pages=10)
    print(f"  pages={r3['pages_fetched']} total_count={r3['total_count']}")
    print(f"  earliest={r3.get('earliest_publishedAt_iso')}  latest={r3.get('latest_publishedAt_iso')}")

    print("\n[4/9] candles 1m BTC-USDT-SWAP (live) ...")
    r4 = probe_candles("BTC-USDT-SWAP")
    print(f"  count={r4['count']} elapsed={r4['elapsed_sec']}s")
    print(f"  newest={r4.get('newest_ts_iso')}  oldest={r4.get('oldest_ts_iso')}")

    print("\n[5/9] history-candles 1m BTC-USDT-SWAP (paginated) ...")
    r5 = probe_candles_history("BTC-USDT-SWAP", target_days=180)
    print(f"  pages={r5['pages_fetched']} rows={r5['rows_fetched']}")
    print(f"  earliest={r5.get('earliest_ts_iso')}  latest={r5.get('latest_ts_iso')} depth_days={r5.get('history_depth_days')}")

    print("\n[6/9] funding-rate-history BTC-USDT-SWAP page=1 ...")
    r6 = probe_funding("BTC-USDT-SWAP")
    print(f"  count={r6['count']} elapsed={r6['elapsed_sec']}s")
    print(f"  newest={r6.get('newest_funding_time_iso')}  oldest={r6.get('oldest_funding_time_iso')}")

    print("\n[7/9] funding-rate-history paginated (up to 10 pages) ...")
    r7 = probe_funding_deep("BTC-USDT-SWAP", max_pages=10)
    print(f"  pages={r7['pages_fetched']} rows={r7['rows_fetched']}")
    print(f"  earliest={r7.get('earliest_funding_time_iso')}  latest={r7.get('latest_funding_time_iso')} depth_days={r7.get('history_depth_days')}")

    print("\n[8/9] open-interest-history (rubik) 1H BTC-USDT-SWAP ...")
    r8 = probe_oi("BTC-USDT-SWAP")
    print(f"  count={r8['count']} elapsed={r8['elapsed_sec']}s")
    print(f"  newest={r8.get('newest_ts_iso')}  oldest={r8.get('oldest_ts_iso')} depth_days={r8.get('history_depth_days')}")

    print("\n[9/9] open-interest-history alt periods + funding-rate (live) + books ...")
    r9a = probe_oi_alt_period("BTC-USDT-SWAP")
    r9b = probe_funding_rate("BTC-USDT-SWAP")
    r9c = probe_mark_price("BTC-USDT-SWAP")
    r9d = probe_ticker("BTC-USDT-SWAP")
    r9e = probe_books("BTC-USDT-SWAP")
    print(f"  OI periods: 5m count={r9a['5m']['count']} | 1H count={r9a['1H']['count']} | 1D count={r9a['1D']['count']}")
    print(f"  funding-rate (live): code={r9b['code']} sample={r9b.get('sample')}")
    print(f"  mark-price: code={r9c['code']} sample_funding_next={r9c.get('sample',{}).get('fundingTime') if r9c.get('sample') else None}")
    print(f"  ticker: code={r9d['code']}")
    print(f"  books: spread_bps={r9e.get('spread_bps')}")

    bundle = {
        "instruments": r1,
        "announcements_p1": r2,
        "announcements_paginated": r3,
        "candles_live": r4,
        "candles_history_paginated": r5,
        "funding_p1": r6,
        "funding_paginated": r7,
        "oi_1H": r8,
        "oi_periods": r9a,
        "funding_rate_live": r9b,
        "mark_price_live": r9c,
        "ticker_live": r9d,
        "books_live": r9e,
    }
    out_path = OUT_DIR / "okx_endpoint_probe.json"
    out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nSaved probe bundle to {out_path}")


if __name__ == "__main__":
    main()
