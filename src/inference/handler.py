"""
AWS Lambda inference handler — PURE PYTHON (stdlib only).

Loads the exported logistic-regression params (model_params.json, packaged in the
deployment zip alongside this file) and scores a request with:

    p = sigmoid( sum_i coef_i * (x_i - mean_i) / scale_i  +  intercept )

No scikit-learn, no numpy, no joblib at runtime — so the deployment package is just
these two small files and needs no Lambda layer. Missing features default to 0.

Observability: every invocation emits a single structured JSON log line (event,
request_id, cold_start, latency_ms, prediction, hof_probability, status) to
CloudWatch Logs. Those JSON fields are auto-discovered by CloudWatch Logs Insights,
so latency percentiles / prediction counts are queryable (see the saved queries in
terraform/observability.tf) and drive the CloudWatch dashboard.
"""
import base64
import json
import logging
import math
import os
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_PARAMS = None
_COLD_START = True  # flipped False after the first invocation in a warm container


def _params():
    """Load + cache the model params once per cold start.

    In the Lambda zip, model_params.json sits next to this file. Tests can point at the
    committed copy via the MODEL_PARAMS_PATH env var.
    """
    global _PARAMS
    if _PARAMS is None:
        path = os.environ.get("MODEL_PARAMS_PATH") or os.path.join(
            os.path.dirname(__file__), "model_params.json"
        )
        with open(path) as f:
            _PARAMS = json.load(f)
    return _PARAMS


def score(features: dict) -> float:
    p = _params()
    z = p["intercept"]
    for i, name in enumerate(p["features"]):
        x = float(features.get(name, 0.0))
        z += p["coef"][i] * (x - p["scaler_mean"][i]) / p["scaler_scale"][i]
    return 1.0 / (1.0 + math.exp(-z))


def handler(event, context):
    """API Gateway HTTP API (payload v2) entry point. POST JSON body of feature values."""
    global _COLD_START
    start = time.perf_counter()
    cold = _COLD_START
    _COLD_START = False
    request_id = getattr(context, "aws_request_id", None)

    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        data = json.loads(body) if isinstance(body, str) else body
        features = data.get("features", data)  # accept {"features": {...}} or a bare {...}
        p = score(features)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "event": "inference",
                    "request_id": request_id,
                    "cold_start": cold,
                    "latency_ms": latency_ms,
                    "prediction": int(p >= 0.5),
                    "hof_probability": round(p, 6),
                    "n_features": len(features) if isinstance(features, dict) else 0,
                    "status": 200,
                }
            )
        )
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"hof_probability": round(p, 6), "prediction": int(p >= 0.5)}),
        }
    except Exception as exc:  # noqa: BLE001 — surface the error to the caller
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            json.dumps(
                {
                    "event": "inference_error",
                    "request_id": request_id,
                    "cold_start": cold,
                    "latency_ms": latency_ms,
                    "error": str(exc),
                    "status": 400,
                }
            )
        )
        return {
            "statusCode": 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": str(exc)}),
        }
