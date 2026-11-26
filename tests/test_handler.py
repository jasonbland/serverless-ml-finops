"""Unit tests for the Lambda inference handler (pure-Python scoring)."""
import base64
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "src" / "train" / "model_params.json"

# Point the handler at the committed params and import it.
os.environ["MODEL_PARAMS_PATH"] = str(PARAMS)
sys.path.insert(0, str(ROOT / "src" / "inference"))
import handler  # noqa: E402


def _call(features):
    event = {"body": json.dumps({"features": features}), "isBase64Encoded": False}
    resp = handler.handler(event, None)
    return resp["statusCode"], json.loads(resp["body"])


def test_hofer_predicts_induction():
    code, body = _call(
        {"bat_H": 3465, "bat_HR": 260, "bat_RBI": 1311, "allstar_games": 14, "award_count": 5, "bat_years": 20}
    )
    assert code == 200
    assert body["prediction"] == 1
    assert body["hof_probability"] > 0.9


def test_scrub_predicts_no():
    code, body = _call({"bat_H": 12, "bat_HR": 0, "bat_years": 1})
    assert code == 200
    assert body["prediction"] == 0


def test_missing_features_default_to_zero():
    code, body = _call({})
    assert code == 200
    assert 0.0 <= body["hof_probability"] <= 1.0


def test_malformed_body_returns_400():
    resp = handler.handler({"body": "not-json", "isBase64Encoded": False}, None)
    assert resp["statusCode"] == 400


def test_base64_encoded_body():
    payload = json.dumps({"features": {"bat_H": 3465, "bat_HR": 260}}).encode()
    event = {"body": base64.b64encode(payload).decode(), "isBase64Encoded": True}
    resp = handler.handler(event, None)
    assert resp["statusCode"] == 200


@pytest.mark.skipif(
    not (ROOT / "src" / "train" / "model.joblib").exists(),
    reason="trained model.joblib not present (skipped in CI; runs locally)",
)
def test_numpy_sklearn_parity():
    """The pure-Python handler must match the scikit-learn pipeline. Runs locally only."""
    joblib = pytest.importorskip("joblib")
    np = pytest.importorskip("numpy")
    pipe = joblib.load(ROOT / "src" / "train" / "model.joblib")
    p = json.loads(PARAMS.read_text())
    rng = np.random.default_rng(0)
    for _ in range(5):
        x = rng.normal(size=len(p["features"]))
        _, body = _call({name: float(v) for name, v in zip(p["features"], x)})
        p_sklearn = float(pipe.predict_proba(x.reshape(1, -1))[0, 1])
        assert abs(body["hof_probability"] - p_sklearn) < 1e-5
