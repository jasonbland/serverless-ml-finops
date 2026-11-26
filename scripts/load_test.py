#!/usr/bin/env python3
"""
Phase 3 — generate a controlled, repeatable load against the inference endpoint so the
pipeline produces enough usage for a stable per-1,000-prediction cost figure.

Pure stdlib (no deps). Varies the payload across a few representative player profiles.

Usage:
  python load_test.py --url "https://<id>.execute-api.us-east-2.amazonaws.com/predict" -n 20000
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# Representative feature payloads (HOFer → scrub, batters + a pitcher) to vary inputs.
SAMPLES = [
    {"bat_H": 3465, "bat_HR": 260, "bat_RBI": 1311, "bat_R": 1923, "bat_SB": 358, "allstar_games": 14, "award_count": 5, "bat_years": 20},
    {"bat_H": 2000, "bat_HR": 200, "bat_RBI": 900, "allstar_games": 3, "bat_years": 12},
    {"bat_H": 500, "bat_HR": 40, "bat_RBI": 200, "bat_years": 6},
    {"pit_W": 300, "pit_SO": 3000, "pit_SHO": 40, "pit_IPouts": 15000, "allstar_games": 8, "bat_years": 18},
    {"bat_H": 12, "bat_HR": 0, "bat_years": 1},
]


def one_request(url: str) -> bool:
    body = json.dumps({"features": random.choice(SAMPLES)}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"content-type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("API_URL"), help="POST endpoint (or set API_URL)")
    ap.add_argument("-n", "--requests", type=int, default=20000)
    ap.add_argument("-c", "--concurrency", type=int, default=20)
    args = ap.parse_args()
    if not args.url:
        sys.exit("Provide --url or set API_URL env var.")

    print(f"Sending {args.requests} requests to {args.url}  (concurrency {args.concurrency}) ...")
    t0 = time.time()
    ok = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = [ex.submit(one_request, args.url) for _ in range(args.requests)]
        for i, f in enumerate(as_completed(futs), 1):
            ok += 1 if f.result() else 0
            if i % 1000 == 0:
                print(f"  {i}/{args.requests}  ok={ok}")
    dt = time.time() - t0
    print(f"\nDone: {ok}/{args.requests} succeeded in {dt:.1f}s ({args.requests / dt:.0f} req/s)")
    print(f"\n>>> Record this prediction count for cost_query.py --predictions : {ok}")
    print(">>> Then wait ~24-48h for Cost Explorer to populate before running cost_query.py.")


if __name__ == "__main__":
    main()
