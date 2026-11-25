#!/usr/bin/env python3
"""
Phase 1 — Train a Hall-of-Fame classifier on the Lahman / Chadwick Baseball Databank.

The model is intentionally minimal. It is a *constant* that the serverless pipeline
serves so the capstone can measure the COST of serving it (per-1,000-prediction cost),
not its predictive quality. It is a logistic regression; its coefficients + scaler are
exported to model_params.json so the Lambda can run inference in **pure numpy** (no
scikit-learn / joblib at runtime), which sidesteps the scikit-learn-in-Lambda packaging
problem.

Outputs (written next to this file):
  data/*.csv          cached raw tables (gitignored)
  model.joblib        the fitted sklearn pipeline (local reference; gitignored)
  model_params.json   {features, scaler_mean, scaler_scale, coef, intercept} for the Lambda
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pylahman as pl
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
import joblib

HERE = Path(__file__).resolve().parent
OUT_MODEL = HERE / "model.joblib"
OUT_PARAMS = HERE / "model_params.json"


def load(table: str) -> pd.DataFrame:
    """Load a Lahman core table via the maintained `pylahman` package (2025 data)."""
    return getattr(pl, table)()


def main() -> None:
    print("Loading Lahman / Chadwick tables ...")
    hof = load("HallOfFame")
    bat = load("Batting")
    pit = load("Pitching")
    allstar = load("AllstarFull")
    awards = load("AwardsPlayers")

    # --- Labels: players who appeared on a HOF ballot (category == Player).
    #     y = 1 if ever inducted, else 0. Using the ballot population (not all players)
    #     keeps the classes from being 1%-vs-99% imbalanced.
    hof_p = hof[hof["category"] == "Player"].copy()
    hof_p["inducted_bin"] = (hof_p["inducted"] == "Y").astype(int)
    labels = hof_p.groupby("playerID")["inducted_bin"].max().reset_index()
    labels.columns = ["playerID", "y"]
    print(f"  labeled players (appeared on a ballot): {len(labels)}  |  inducted: {int(labels['y'].sum())}")

    # --- Career batting features (sums across seasons)
    bat_cols = ["G", "AB", "R", "H", "2B", "3B", "HR", "RBI", "SB", "BB", "SO"]
    b = bat.groupby("playerID")[bat_cols].sum()
    b["AVG"] = np.where(b["AB"] > 0, b["H"] / b["AB"], 0.0)
    b["years"] = bat.groupby("playerID")["yearID"].nunique()
    b = b.add_prefix("bat_")

    # --- Career pitching features
    p = pit.groupby("playerID").agg(
        pit_W=("W", "sum"),
        pit_L=("L", "sum"),
        pit_G=("G", "sum"),
        pit_SV=("SV", "sum"),
        pit_SO=("SO", "sum"),
        pit_SHO=("SHO", "sum"),
        pit_IPouts=("IPouts", "sum"),
        pit_ERA=("ERA", "mean"),
    )

    # --- All-Star game appearances + total award count
    asg = allstar.groupby("playerID").size().rename("allstar_games")
    awd = awards.groupby("playerID").size().rename("award_count")

    # --- Assemble feature matrix
    df = labels.set_index("playerID").join([b, p, asg, awd], how="left").fillna(0.0)
    y = df.pop("y").to_numpy()
    X = df.to_numpy(dtype=float)
    feats = list(df.columns)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    pipe.fit(X_tr, y_tr)

    pred = pipe.predict(X_te)
    proba = pipe.predict_proba(X_te)[:, 1]
    print("\n=== Validation (model quality is NOT the study object — just confirming it works) ===")
    print(classification_report(y_te, pred, digits=3))
    print(f"ROC-AUC : {roc_auc_score(y_te, proba):.3f}")
    print(f"Accuracy: {(pred == y_te).mean():.3f}")

    joblib.dump(pipe, OUT_MODEL)

    # --- Export params so the Lambda can score in pure numpy (no sklearn at runtime)
    scaler = pipe.named_steps["scaler"]
    clf = pipe.named_steps["clf"]
    params = {
        "features": feats,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
        "note": "p = sigmoid(sum(coef_i * (x_i - scaler_mean_i)/scaler_scale_i) + intercept); x in 'features' order",
    }
    OUT_PARAMS.write_text(json.dumps(params, indent=2))
    print(f"\nSaved {OUT_MODEL.name} and {OUT_PARAMS.name}  ({len(feats)} features).")


if __name__ == "__main__":
    main()
