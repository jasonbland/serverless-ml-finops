#!/usr/bin/env python3
"""
Post-load-test monitoring readout — pulls CloudWatch metrics for the inference Lambda
(and the HTTP API, if an API URL is given) over a recent window and prints a Markdown
table. In CI it's appended to $GITHUB_STEP_SUMMARY so every pipeline run shows its own
Lambda health — no console needed. Locally it just prints to stdout.

The HTTP API id is the first label of the API endpoint host
(https://<api-id>.execute-api.<region>.amazonaws.com/...), so --api-url is all we need
to pull the API Gateway metrics too — no extra lookup, no extra IAM permission.

Usage:
    python scripts/metrics_summary.py --minutes 20 --api-url "$API_URL"
Needs: cloudwatch:GetMetricData (granted to the CI role in github_oidc.tf).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from urllib.parse import urlparse

import boto3


def _api_id_from_url(url: str) -> str | None:
    if not url:
        return None
    host = urlparse(url).hostname or ""
    if ".execute-api." in host:
        return host.split(".")[0]
    return None


def _queries(function: str, api_id: str | None):
    """Build the GetMetricData query list. Each id maps to a column in the output."""
    lam = [("FunctionName", function)]
    q = [
        ("invocations", "AWS/Lambda", "Invocations", lam, "Sum"),
        ("errors", "AWS/Lambda", "Errors", lam, "Sum"),
        ("throttles", "AWS/Lambda", "Throttles", lam, "Sum"),
        ("dur_avg", "AWS/Lambda", "Duration", lam, "Average"),
        ("dur_p50", "AWS/Lambda", "Duration", lam, "p50"),
        ("dur_p99", "AWS/Lambda", "Duration", lam, "p99"),
        ("dur_max", "AWS/Lambda", "Duration", lam, "Maximum"),
    ]
    if api_id:
        api = [("ApiId", api_id)]
        q += [
            ("api_count", "AWS/ApiGateway", "Count", api, "Sum"),
            ("api_4xx", "AWS/ApiGateway", "4xx", api, "Sum"),
            ("api_5xx", "AWS/ApiGateway", "5xx", api, "Sum"),
            ("api_lat_p50", "AWS/ApiGateway", "Latency", api, "p50"),
            ("api_lat_p99", "AWS/ApiGateway", "Latency", api, "p99"),
        ]
    return q


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--function", default="hof-inference")
    ap.add_argument("--api-url", default="", help="API endpoint; the api-id is parsed from it")
    ap.add_argument("--minutes", type=int, default=20, help="look-back window")
    ap.add_argument("--region", default="us-east-2")
    ap.add_argument("--label", default="", help="optional tag for the header (e.g. 'memory=256 MB')")
    args = ap.parse_args()

    api_id = _api_id_from_url(args.api_url)
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(minutes=args.minutes)

    cw = boto3.client("cloudwatch", region_name=args.region)
    specs = _queries(args.function, api_id)
    mdq = [
        {
            "Id": sid,
            "MetricStat": {
                "Metric": {
                    "Namespace": ns,
                    "MetricName": name,
                    "Dimensions": [{"Name": k, "Value": v} for k, v in dims],
                },
                "Period": 60,
                "Stat": stat,
            },
            "ReturnData": True,
        }
        for sid, ns, name, dims, stat in specs
    ]

    resp = cw.get_metric_data(
        MetricDataQueries=mdq, StartTime=start, EndTime=end, ScanBy="TimestampAscending"
    )

    # Aggregate the per-minute datapoints: Sum metrics add up; latency/duration we take
    # the max of the per-minute stat as the window-level figure.
    sum_ids = {"invocations", "errors", "throttles", "api_count", "api_4xx", "api_5xx"}
    vals = {}
    for r in resp["MetricDataResults"]:
        pts = r["Values"]
        if not pts:
            vals[r["Id"]] = 0.0
        elif r["Id"] in sum_ids:
            vals[r["Id"]] = sum(pts)
        else:
            vals[r["Id"]] = max(pts)

    def g(k):
        return vals.get(k, 0.0)

    title = f"## 📊 Metrics summary — last {args.minutes} min"
    if args.label:
        title += f" · **{args.label}**"
    lines = [
        title,
        "",
        f"Window: `{start:%Y-%m-%d %H:%M}`–`{end:%H:%M} UTC` · region `{args.region}` · function `{args.function}`"
        + (f" · api `{api_id}`" if api_id else " · _(no API URL — Lambda metrics only)_"),
        "",
        "| Metric | Value |",
        "|--------|------:|",
        f"| Invocations | {g('invocations'):.0f} |",
        f"| Errors | {g('errors'):.0f} |",
        f"| Throttles | {g('throttles'):.0f} |",
        f"| Duration avg (ms) | {g('dur_avg'):.1f} |",
        f"| Duration p50 (ms) | {g('dur_p50'):.1f} |",
        f"| Duration p99 (ms) | {g('dur_p99'):.1f} |",
        f"| Duration max (ms) | {g('dur_max'):.1f} |",
    ]
    if api_id:
        lines += [
            f"| API requests | {g('api_count'):.0f} |",
            f"| API 4xx | {g('api_4xx'):.0f} |",
            f"| API 5xx | {g('api_5xx'):.0f} |",
            f"| API latency p50 (ms) | {g('api_lat_p50'):.1f} |",
            f"| API latency p99 (ms) | {g('api_lat_p99'):.1f} |",
        ]
    lines += [
        "",
        f"🔗 [Open the CloudWatch dashboard](https://{args.region}.console.aws.amazon.com/cloudwatch/home?region={args.region}#dashboards/dashboard/capstone-mlfinops)",
    ]
    if g("invocations") == 0:
        lines += [
            "",
            "> ⚠️ Zero invocations in the window. Metrics lag ~1–2 min — if you just ran the load test, wait and re-run; otherwise check the API URL / region.",
        ]

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
