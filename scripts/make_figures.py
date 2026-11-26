#!/usr/bin/env python3
"""
Phase 5 — turn dashboards/*.csv into committed matplotlib PNG figures (no AWS).

Reproducible-from-code charts for the paper/README. Power BI is the separate manual
layer; these are the versioned, regenerable figures. Skips any chart whose CSV is
missing/empty so it is safe to run before cost data has landed.
"""
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless (CI)
import matplotlib.pyplot as plt  # noqa: E402

D = Path(__file__).resolve().parent.parent / "dashboards"


def read(name):
    p = D / name
    if not p.exists():
        return None
    with open(p) as f:
        return list(csv.DictReader(f))


def fig_cost_by_service():
    rows = read("cost_by_service.csv")
    if not rows:
        return
    rows = [r for r in rows if float(r["cost_usd"]) > 0] or rows
    svc = [r["service"] for r in rows]
    cost = [float(r["cost_usd"]) for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(svc[::-1], cost[::-1], color="#2a78d6")
    ax.set_xlabel("Cost (USD)")
    ax.set_title("AWS cost by service (Project=capstone)")
    fig.tight_layout()
    fig.savefig(D / "cost_by_service.png", dpi=150)
    plt.close(fig)
    print("wrote cost_by_service.png")


def fig_cost_over_time():
    rows = read("cost_over_time.csv")
    if not rows:
        return
    series = defaultdict(dict)
    for r in rows:
        series[r["service"]][r["date"]] = float(r["cost_usd"])
    dates = sorted({r["date"] for r in rows})
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for svc, dmap in series.items():
        ax.plot(dates, [dmap.get(d, 0.0) for d in dates], marker="o", label=svc)
    ax.set_ylabel("Daily cost (USD)")
    ax.set_title("Daily cost by service")
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(D / "cost_over_time.png", dpi=150)
    plt.close(fig)
    print("wrote cost_over_time.png")


def fig_unit_cost():
    rows = read("unit_cost.csv")
    if not rows:
        return
    m = {r["metric"]: r["value_usd"] for r in rows}
    labels = ["actual billed", "list price"]
    vals = [float(m.get("actual_billed_per_1000", 0)), float(m.get("list_price_per_1000", 0))]
    fig, ax = plt.subplots(figsize=(5, 4.5))
    bars = ax.bar(labels, vals, color=["#9ec5f4", "#184f95"])
    ax.set_ylabel("USD per 1,000 predictions")
    ax.set_title("Cost per 1,000 predictions")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"${v:.4f}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    fig.savefig(D / "unit_cost.png", dpi=150)
    plt.close(fig)
    print("wrote unit_cost.png")


def main():
    if not any((D / n).exists() for n in ("cost_by_service.csv", "cost_over_time.csv", "unit_cost.csv")):
        print("No dashboards/*.csv yet — run cost-query first. Nothing to plot.")
        return
    fig_cost_by_service()
    fig_cost_over_time()
    fig_unit_cost()
    print(f"Figures written to {D}")


if __name__ == "__main__":
    main()
