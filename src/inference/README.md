# src/inference/ — Phase 2 (not yet built)

`handler.py` — the Lambda handler. Loads `model_params.json` (committed) and scores a
request in **pure numpy**: `p = sigmoid(coef . ((x - mean)/scale) + intercept)`. No
scikit-learn or joblib at runtime, so the deployment package stays tiny and avoids the
scikit-learn-in-Lambda packaging problem.
