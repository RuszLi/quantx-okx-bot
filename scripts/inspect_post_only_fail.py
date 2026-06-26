"""Quick inspect: just list post-only FAIL symbols."""
import csv
with open("reports/v3_output/_probe/feasibility_table.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

fails = [r for r in rows if r["can_post_only_fill"] != "True"]
print(f"Total post-only FAIL: {len(fails)}")
print()
for r in fails:
    print(f"  {r['inst_id']:30s}  spread_bps={float(r['spread_bps']):8.2f}  last={r['last_price']:>10s}  vol24h=${float(r['vol_24h_usdt'] or 0):>14,.0f}  list={r['list_time_iso'][:10]}")
