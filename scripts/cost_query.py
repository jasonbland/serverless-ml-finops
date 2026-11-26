#!/usr/bin/env python3
"""
Phase 3/5 — pull cost + usage from AWS Cost Explorer (filtered by Project=capstone),
normalize to cost per 1,000 predictions, and write Power-BI-ready CSVs to dashboards/.

Cost Explorer is a GLOBAL service, so the `ce` client is pinned to us-east-1 even
though the resources live in us-east-2. The `Project` cost-allocation tag must be
ACTIVATED in Billing (post-deploy, ~24h) for the tag filter + per-tag grouping to work.

Why two cost numbers: at this volume AWS Free Tier often makes the *billed* cost $0.
That's itself a serverless-economics finding, but it doesn't generalize — so this also
computes a **list-price** unit cost from measured usage x published rates. Report the
list-price figure as the headline and note the $0 actual bill.

Usage:
  python cost_query.py --predictions 20000 --start 2026-11-25 --end 2026-11-28
"""
import argparse
import csv
import datetime as dt
from pathlib import Path

import boto3

OUT = Path(__file__).resolve().parent.parent / "dashboards"
TAG_FILTER = {"Tags": {"Key": "Project", "Values": ["capstone"]}}

# Best-effort us-east-2 (USE2) list prices, matched by usage-type substring.
# VERIFY against the raw usage types this script prints, then refine before the Final.
PRICE_PER_UNIT = {
    "Lambda-GB-Second": 1.66667e-5,   # $/GB-second
    "Request": 2.0e-7,                # Lambda request  ($0.20 / 1M)
    "ApiGateway": 1.0e-6,             # HTTP API request ($1.00 / 1M)
    "TimedStorage": 2.3e-11,          # S3 storage, negligible
    "DataProcessing-Bytes": 0.0,
}


def ce_client():
    return boto3.client("ce", region_name="us-east-1")


def cost_by_service(ce, start, end):
    r = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end}, Granularity="DAILY",
        Metrics=["UnblendedCost"], Filter=TAG_FILTER,
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    rows = []
    for day in r["ResultsByTime"]:
        date = day["TimePeriod"]["Start"]
        for g in day["Groups"]:
            rows.append({"date": date, "service": g["Keys"][0],
                         "cost_usd": float(g["Metrics"]["UnblendedCost"]["Amount"])})
    return rows


def usage_by_type(ce, start, end):
    r = ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end}, Granularity="DAILY",
        Metrics=["UsageQuantity"], Filter=TAG_FILTER,
        GroupBy=[{"Type": "DIMENSION", "Key": "USAGE_TYPE"}],
    )
    totals = {}
    for day in r["ResultsByTime"]:
        for g in day["Groups"]:
            ut = g["Keys"][0]
            totals[ut] = totals.get(ut, 0.0) + float(g["Metrics"]["UsageQuantity"]["Amount"])
    return totals


def list_price(usage: dict) -> float:
    total = 0.0
    for ut, qty in usage.items():
        for key, rate in PRICE_PER_UNIT.items():
            if key in ut:
                total += qty * rate
                break
    return total


def main() -> None:
    today = dt.date.today()
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictions", type=int, required=True, help="predictions served in the window")
    ap.add_argument("--start", default=str(today - dt.timedelta(days=7)))
    ap.add_argument("--end", default=str(today + dt.timedelta(days=1)))
    ap.add_argument("--gate", action="store_true",
                    help="exit 2 (not 0) if no tagged usage has landed yet — for CI polling")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    ce = ce_client()

    rows = cost_by_service(ce, args.start, args.end)
    usage = usage_by_type(ce, args.start, args.end)
    net_total = sum(r["cost_usd"] for r in rows)
    list_total = list_price(usage)

    # Readiness gate: Cost Explorer lags ~24-48h. If nothing has landed, signal "not ready"
    # (exit 2) so a CI poll can skip quietly instead of writing a misleading $0 artifact.
    if args.gate and net_total == 0 and sum(usage.values()) == 0:
        print(f"DATA NOT READY — no tagged usage for {args.start}..{args.end} yet "
              "(Cost Explorer lag, or the Project tag isn't active). Will retry on the next poll.")
        raise SystemExit(2)

    # --- cost_over_time.csv
    with open(OUT / "cost_over_time.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "service", "cost_usd"])
        w.writeheader(); w.writerows(rows)

    # --- cost_by_service.csv
    by_svc = {}
    for r in rows:
        by_svc[r["service"]] = by_svc.get(r["service"], 0.0) + r["cost_usd"]
    with open(OUT / "cost_by_service.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["service", "cost_usd", "pct_of_total"])
        for svc, amt in sorted(by_svc.items(), key=lambda x: -x[1]):
            w.writerow([svc, f"{amt:.6f}", f"{(amt / net_total * 100 if net_total else 0):.1f}"])

    # --- unit_cost.csv
    net_per_1k = net_total / args.predictions * 1000 if args.predictions else 0
    list_per_1k = list_total / args.predictions * 1000 if args.predictions else 0
    with open(OUT / "unit_cost.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["metric", "value_usd"])
        w.writerow(["predictions", args.predictions])
        w.writerow(["actual_billed_total", f"{net_total:.6f}"])
        w.writerow(["actual_billed_per_1000", f"{net_per_1k:.6f}"])
        w.writerow(["list_price_total", f"{list_total:.6f}"])
        w.writerow(["list_price_per_1000", f"{list_per_1k:.6f}"])

    print(f"Window {args.start}..{args.end}  |  predictions: {args.predictions}")
    print(f"Actual billed (free-tier net): ${net_total:.6f}  → ${net_per_1k:.6f} / 1,000")
    print(f"List-price (usage x rates)   : ${list_total:.6f}  → ${list_per_1k:.6f} / 1,000  (headline)")
    print("\nRaw usage types found (verify the price map against these):")
    for ut, qty in sorted(usage.items(), key=lambda x: -x[1]):
        print(f"  {ut:40s} {qty:,.4f}")
    if net_total == 0:
        print("\nNOTE: $0 billed — Free Tier absorbed it. Report the LIST-PRICE per-1,000 as the"
              "\ngeneralizable figure; the $0 bill is a finding about serverless cost at low volume.")
    print(f"\nWrote CSVs to {OUT}")


if __name__ == "__main__":
    main()
