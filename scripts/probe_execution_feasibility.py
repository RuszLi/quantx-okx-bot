"""V3 §18.3 Execution feasibility probe.

For every live SWAP contract on OKX, evaluate:
- can_open_position(equity=$7, leverage=lever, risk_R=0.30, stop_distance_pct=5%)
- can_place_hard_stop (tickSz relative to price)
- can_post_only_fill (order book spread in bps)

Output: reports/v3_output/_probe/feasibility_table.csv + feasibility_summary.json
"""

from __future__ import annotations

import csv
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import httpx

OKX = "https://www.okx.com"
OUT = Path("reports/v3_output/_probe")
OUT.mkdir(parents=True, exist_ok=True)

# Phase α constraints (per §6.1 of plan)
EQUITY_USD = 7.0
RISK_PER_TRADE_R_ALPHA = 0.30  # Phase α
ASSUMED_STOP_DISTANCE_PCT = 0.05  # 5% stop loss assumption (worst-case bound)

# Hard-stop feasibility
TICKSZ_MAX_PCT_OF_PRICE = 0.005  # tickSz must be < 0.5% of price to place usable stop

# Post-only feasibility (spread threshold)
SPREAD_BPS_MAX = 5.0


def http_get_json(url: str, timeout: float = 30.0) -> tuple[dict, int]:
    headers = {"User-Agent": "okx-bot/1.0", "Accept": "application/json"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url, headers=headers)
            try:
                return r.json(), r.status_code
            except Exception:
                return {"_raw": r.text}, r.status_code
    except Exception as e:
        return {"_error": str(e)}, 0


def ts_ms_to_iso(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def fetch_instruments(inst_type: str = "SWAP") -> list[dict]:
    payload, _ = http_get_json(
        OKX + "/api/v5/public/instruments?" + urllib.parse.urlencode({"instType": inst_type})
    )
    return payload.get("data") or []


def fetch_tickers() -> dict[str, dict]:
    """Fetch tickers for all SWAP contracts (24h volume + last price)."""
    payload, _ = http_get_json(OKX + "/api/v5/market/tickers?instType=SWAP")
    out = {}
    for x in payload.get("data") or []:
        out[x.get("instId")] = x
    return out


def fetch_book(inst_id: str, sz: int = 5) -> dict | None:
    payload, _ = http_get_json(
        OKX + "/api/v5/market/books?" + urllib.parse.urlencode({"instId": inst_id, "sz": sz})
    )
    data = payload.get("data") or []
    return data[0] if data else None


def compute_book_spread(book: dict) -> tuple[float, float, float, float]:
    """Return (best_bid, best_ask, mid, spread_bps) or NaN."""
    try:
        asks = book.get("asks") or []
        bids = book.get("bids") or []
        if not asks or not bids:
            return (math.nan, math.nan, math.nan, math.nan)
        best_ask = float(asks[0][0])
        best_bid = float(bids[0][0])
        mid = (best_ask + best_bid) / 2
        spread_bps = (best_ask - best_bid) / mid * 10000 if mid > 0 else math.nan
        return (best_bid, best_ask, mid, spread_bps)
    except Exception:
        return (math.nan, math.nan, math.nan, math.nan)


def evaluate_symbol(
    inst: dict,
    ticker: dict | None,
    book: dict | None,
    equity: float = EQUITY_USD,
    risk_R: float = RISK_PER_TRADE_R_ALPHA,
    stop_pct: float = ASSUMED_STOP_DISTANCE_PCT,
) -> dict:
    """Return one feasibility record."""
    inst_id = inst.get("instId", "")
    state = inst.get("state", "")
    settle_ccy = inst.get("settleCcy", "")
    quote_ccy = inst.get("quoteCcy") or inst.get("settleCcy")
    try:
        ct_val = float(inst.get("ctVal") or 0)
    except Exception:
        ct_val = 0.0
    try:
        min_sz = float(inst.get("minSz") or 0)
    except Exception:
        min_sz = 0.0
    try:
        lot_sz = float(inst.get("lotSz") or min_sz or 0)
    except Exception:
        lot_sz = min_sz
    try:
        tick_sz = float(inst.get("tickSz") or 0)
    except Exception:
        tick_sz = 0.0
    try:
        lever_max = float(inst.get("lever") or 0)
    except Exception:
        lever_max = 0.0
    list_time_ms = int(inst.get("listTime") or 0)

    # Ticker data
    last_price = 0.0
    vol_24h_usdt = 0.0
    if ticker:
        try:
            last_price = float(ticker.get("last") or 0)
        except Exception:
            last_price = 0.0
        try:
            vol_24h_usdt = float(ticker.get("volCcy24h") or 0) * last_price
        except Exception:
            vol_24h_usdt = 0.0
        if not vol_24h_usdt:
            try:
                vol_24h_usdt = float(ticker.get("vol24h") or 0) * last_price
            except Exception:
                pass

    # Book spread
    best_bid = best_ask = mid = math.nan
    spread_bps = math.nan
    if book:
        best_bid, best_ask, mid, spread_bps = compute_book_spread(book)

    # Fallback: if no ticker price, use mid from book
    if not last_price and not math.isnan(mid):
        last_price = mid

    # === Core feasibility computations ===
    # Minimum notional (in quote currency) for 1 lot
    notional_min_per_lot = ct_val * min_sz * last_price if last_price > 0 else math.nan
    # Maximum notional equity can support at lever_max
    notional_max_at_lever = equity * lever_max
    # Maximum notional equity can support with risk cap (assume stop_pct worst case)
    # loss_per_lot = notional_min_per_lot * stop_pct
    # acceptable_loss = equity * risk_R
    # → can_open_with_risk_cap = notional_min_per_lot * stop_pct <= equity * risk_R
    acceptable_loss = equity * risk_R
    loss_per_lot_at_stop = notional_min_per_lot * stop_pct if notional_min_per_lot else math.nan

    can_open_at_lever_cap = (
        notional_min_per_lot <= notional_max_at_lever
        if notional_min_per_lot and notional_max_at_lever
        else False
    )
    can_open_with_risk_cap = (
        loss_per_lot_at_stop <= acceptable_loss
        if not math.isnan(loss_per_lot_at_stop)
        else False
    )
    # can_open_position: BOTH constraints met (need to actually place min 1 lot
    # AND the worst-case loss must be ≤ equity × risk_R)
    can_open_position = bool(can_open_at_lever_cap and can_open_with_risk_cap)

    # can_place_hard_stop: tickSz < 0.5% of price
    can_place_hard_stop = (
        tick_sz > 0
        and last_price > 0
        and (tick_sz / last_price) <= TICKSZ_MAX_PCT_OF_PRICE
    )

    # can_post_only_fill: spread < 5 bps
    can_post_only_fill = (
        not math.isnan(spread_bps) and spread_bps <= SPREAD_BPS_MAX
    )

    # How many lots can we hold given risk cap?
    # max_lots_by_risk = floor(equity * risk_R / (notional_min_per_lot * stop_pct))
    if (
        notional_min_per_lot
        and notional_min_per_lot > 0
        and stop_pct > 0
    ):
        max_lots_by_risk = int(acceptable_loss / (notional_min_per_lot * stop_pct))
        max_lots_by_lever = int(notional_max_at_lever / notional_min_per_lot) if notional_min_per_lot else 0
        max_lots = max(0, min(max_lots_by_risk, max_lots_by_lever))
    else:
        max_lots = 0

    return {
        "inst_id": inst_id,
        "state": state,
        "settle_ccy": settle_ccy,
        "quote_ccy": quote_ccy,
        "list_time_iso": ts_ms_to_iso(list_time_ms),
        "list_time_ms": list_time_ms,
        "ct_val": ct_val,
        "min_sz": min_sz,
        "lot_sz": lot_sz,
        "tick_sz": tick_sz,
        "lever_max": lever_max,
        "last_price": last_price,
        "vol_24h_usdt": round(vol_24h_usdt, 2),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_bps": spread_bps,
        "notional_min_per_lot": notional_min_per_lot,
        "notional_max_at_lever": notional_max_at_lever,
        "loss_per_lot_at_stop_5pct": loss_per_lot_at_stop,
        "acceptable_loss_usd": acceptable_loss,
        "max_lots_at_risk_cap": max_lots,
        "can_open_at_lever_cap": can_open_at_lever_cap,
        "can_open_with_risk_cap": can_open_with_risk_cap,
        "can_open_position": can_open_position,
        "can_place_hard_stop": can_place_hard_stop,
        "can_post_only_fill": can_post_only_fill,
        "tickSz_pct_of_price": (tick_sz / last_price) if last_price > 0 and tick_sz > 0 else math.nan,
    }


def main():
    print("Fetching instruments SWAP ...")
    insts = fetch_instruments("SWAP")
    print(f"  total={len(insts)}")
    live_insts = [x for x in insts if x.get("state") == "live"]
    print(f"  live={len(live_insts)}")

    print("\nFetching tickers SWAP ...")
    tickers = fetch_tickers()
    print(f"  tickers={len(tickers)}")

    # Candidate universe:
    # - All live USDT-settled SWAP (most relevant for $7 equity)
    # - Plus all 2026-06 new listings (Strategy A universe)
    candidates = []
    for inst in live_insts:
        settle = inst.get("settleCcy", "")
        if settle == "USDT":
            candidates.append(inst)
    # Dedup
    seen = {x.get("instId") for x in candidates}
    for inst in live_insts:
        if inst.get("instId") in seen:
            continue
        lt = int(inst.get("listTime") or 0)
        if lt >= 1748736000000:  # 2025-06-01 UTC, broad enough
            candidates.append(inst)
            seen.add(inst.get("instId"))
    print(f"\nCandidate universe: {len(candidates)}")

    # Sort by 24h vol desc (use ticker)
    def vol_key(x):
        t = tickers.get(x.get("instId"))
        if not t:
            return 0.0
        try:
            lp = float(t.get("last") or 0)
            return float(t.get("vol24h") or 0) * lp
        except Exception:
            return 0.0

    candidates.sort(key=vol_key, reverse=True)

    # Probe top N + all 2026-06 listings with books
    TOP_N_VOL = 60  # top 60 by vol (B/C/D/E/H/K)
    JUNE_LISTINGS_N = 80  # 2026-06 listings (A universe)
    june_listings = [
        x for x in candidates
        if int(x.get("listTime") or 0) >= 1748736000000  # 2025-06-01
    ][:JUNE_LISTINGS_N]
    top_vol = candidates[:TOP_N_VOL]
    probe_set = {x.get("instId"): x for x in (top_vol + june_listings)}.values()
    print(f"Probing {len(probe_set)} symbols (top {TOP_N_VOL} by vol + {len(june_listings)} 2025-06+ listings) ...")

    records = []
    for i, inst in enumerate(probe_set, 1):
        inst_id = inst.get("instId")
        ticker = tickers.get(inst_id)
        # Book probe (rate-limit friendly: 200ms between)
        book = fetch_book(inst_id, sz=5)
        rec = evaluate_symbol(inst, ticker, book)
        records.append(rec)
        if i % 20 == 0:
            print(f"  [{i}/{len(probe_set)}] latest={inst_id} can_open={rec['can_open_position']}")
        time.sleep(0.05)

    # Save CSV
    csv_path = OUT / "feasibility_table.csv"
    fieldnames = list(records[0].keys())
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if (isinstance(v, float) and math.isnan(v)) else v) for k, v in r.items()})
    print(f"\nSaved CSV to {csv_path}")

    # Summary stats
    total = len(records)
    open_ok = sum(1 for r in records if r["can_open_position"])
    hard_stop_ok = sum(1 for r in records if r["can_place_hard_stop"])
    post_only_ok = sum(1 for r in records if r["can_post_only_fill"])
    all_three = sum(1 for r in records if r["can_open_position"] and r["can_place_hard_stop"] and r["can_post_only_fill"])

    # Strategy-relevant subsets
    june_records = [r for r in records if int(r["list_time_ms"] or 0) >= 1748736000000]
    june_open_ok = sum(1 for r in june_records if r["can_open_position"])

    top_vol_records = records[:TOP_N_VOL]
    top_vol_open_ok = sum(1 for r in top_vol_records if r["can_open_position"])

    summary = {
        "probe_time_utc": datetime.now(timezone.utc).isoformat(),
        "equity_usd": EQUITY_USD,
        "risk_R": RISK_PER_TRADE_R_ALPHA,
        "assumed_stop_pct": ASSUMED_STOP_DISTANCE_PCT,
        "tickSz_max_pct": TICKSZ_MAX_PCT_OF_PRICE,
        "spread_bps_max": SPREAD_BPS_MAX,
        "total_probed": total,
        "can_open_position_count": open_ok,
        "can_place_hard_stop_count": hard_stop_ok,
        "can_post_only_fill_count": post_only_ok,
        "all_three_count": all_three,
        "june_listings_probed": len(june_records),
        "june_listings_can_open": june_open_ok,
        "top_vol_probed": len(top_vol_records),
        "top_vol_can_open": top_vol_open_ok,
        "candidates_can_open_all_three": [
            r["inst_id"] for r in records
            if r["can_open_position"] and r["can_place_hard_stop"] and r["can_post_only_fill"]
        ][:60],
        "june_candidates_can_open_all_three": [
            r["inst_id"] for r in june_records
            if r["can_open_position"] and r["can_place_hard_stop"] and r["can_post_only_fill"]
        ][:60],
        "top_vol_candidates_can_open_all_three": [
            r["inst_id"] for r in top_vol_records
            if r["can_open_position"] and r["can_place_hard_stop"] and r["can_post_only_fill"]
        ][:60],
    }
    json_path = OUT / "feasibility_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Saved summary JSON to {json_path}")
    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
