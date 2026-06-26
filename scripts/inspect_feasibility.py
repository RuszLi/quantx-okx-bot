"""Inspect feasibility_table.csv to summarize stats for §18.3 report."""
import csv
import statistics
from collections import Counter

with open("reports/v3_output/_probe/feasibility_table.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

print("=" * 70)
print("Post-only FAIL samples (17 expected):")
print("=" * 70)
for r in rows:
    if r["can_post_only_fill"] != "True":
        print(f"  {r['inst_id']:30s}  spread_bps={r['spread_bps']:>10s}  last={r['last_price']:>10s}  vol24h={r['vol_24h_usdt']:>14s}  list={r['list_time_iso']}")

print()
print("=" * 70)
print("Top 10 by vol (feasibility PASS samples):")
print("=" * 70)
for r in rows[:10]:
    print(f"  {r['inst_id']:25s}  spread_bps={float(r['spread_bps']):6.2f}  notional_min={float(r['notional_min_per_lot']):8.4f}  max_lots={r['max_lots_at_risk_cap']:>4s}  loss@5%={float(r['loss_per_lot_at_stop_5pct']):6.4f}")

print()
print("=" * 70)
print("Notional_min distribution:")
print("=" * 70)
nm = [float(r["notional_min_per_lot"]) for r in rows if r["notional_min_per_lot"]]
print(f"  n={len(nm)}  min={min(nm):.4f}  p25={sorted(nm)[len(nm)//4]:.4f}  median={statistics.median(nm):.4f}  p75={sorted(nm)[3*len(nm)//4]:.4f}  max={max(nm):.4f}")

print()
print("=" * 70)
print("Spread_bps distribution:")
print("=" * 70)
sb = [float(r["spread_bps"]) for r in rows if r["spread_bps"]]
print(f"  n={len(sb)}  min={min(sb):.3f}  p25={sorted(sb)[len(sb)//4]:.3f}  median={statistics.median(sb):.3f}  p75={sorted(sb)[3*len(sb)//4]:.3f}  max={max(sb):.3f}")

print()
print("=" * 70)
print("tickSz_pct_of_price distribution:")
print("=" * 70)
tp = [float(r["tickSz_pct_of_price"]) for r in rows if r["tickSz_pct_of_price"]]
print(f"  n={len(tp)}  min={min(tp):.6f}  median={statistics.median(tp):.6f}  max={max(tp):.6f}")

print()
print("=" * 70)
print("lever_max distribution:")
print("=" * 70)
print(f"  {Counter(r['lever_max'] for r in rows)}")

print()
print("=" * 70)
print("settleCcy distribution:")
print("=" * 70)
print(f"  {Counter(r['settle_ccy'] for r in rows)}")

print()
print("=" * 70)
print("max_lots_at_risk_cap distribution:")
print("=" * 70)
ml = sorted([int(r["max_lots_at_risk_cap"]) for r in rows if r["max_lots_at_risk_cap"]])
print(f"  n={len(ml)}  min={ml[0]}  p25={ml[len(ml)//4]}  median={ml[len(ml)//2]}  p75={ml[3*len(ml)//4]}  max={ml[-1]}")

# Per-strategy candidate pick (10 symbols each)
print()
print("=" * 70)
print("Per-strategy candidate universe (10 each):")
print("=" * 70)
# A: 2025-06+ new listings, top by vol, can_open + hard_stop + post_only
june = [r for r in rows if r["list_time_iso"] and r["list_time_iso"] >= "2025-06" and r["can_post_only_fill"]=="True"]
june.sort(key=lambda r: -float(r["vol_24h_usdt"] or 0))
print("\n[A] Strategy A (listing fade) — 2025-06+ new listings, post_only PASS, top 10 by vol:")
for r in june[:10]:
    print(f"  {r['inst_id']:25s}  list={r['list_time_iso'][:10]}  spread={float(r['spread_bps']):5.2f}bps  vol24h=${float(r['vol_24h_usdt']):,.0f}")

# B/E: top 20 by vol, post_only PASS
be = [r for r in rows if r["can_post_only_fill"]=="True"]
be.sort(key=lambda r: -float(r["vol_24h_usdt"] or 0))
print("\n[B/E] Strategy B/E (funding/pre-funding) — top 20 by vol, post_only PASS:")
for r in be[:20]:
    print(f"  {r['inst_id']:25s}  spread={float(r['spread_bps']):5.2f}bps  vol24h=${float(r['vol_24h_usdt']):,.0f}  max_lots={r['max_lots_at_risk_cap']}")

# C/D: top 15 by vol
print("\n[C/D] Strategy C/D (beta decouple / weekend wick) — same pool as B/E (top 15)")
for r in be[:15]:
    print(f"  {r['inst_id']:25s}  spread={float(r['spread_bps']):5.2f}bps  vol24h=${float(r['vol_24h_usdt']):,.0f}")

# H: top 10 by vol (OI rich)
print("\n[H] Strategy H (OI velocity) — top 10 by vol:")
for r in be[:10]:
    print(f"  {r['inst_id']:25s}  spread={float(r['spread_bps']):5.2f}bps  vol24h=${float(r['vol_24h_usdt']):,.0f}")
