# serverless-ml-finops

A reproducible, serverless **MLOps + FinOps** pipeline on AWS that serves a trivial
machine-learning model and **measures the cost of serving it** — cost per 1,000
predictions, broken down by service.

> CMIT-590 Information Technology Capstone (Champlain MSIT). The served model (a
> Baseball Hall-of-Fame classifier on the Lahman dataset) is a deliberately minimal
> *constant* — the research question is about the **cost** of the serving pipeline,
> not the model's accuracy.

## Architecture (serverless)

```
client ──> API Gateway (HTTP API) ──> AWS Lambda (pure-numpy inference) ──> prediction
                                          │  loads model_params.json
                                          ▼
                             S3 (data + model) · CloudWatch (logs)
Cost: AWS Budgets + cost-allocation tag (Project=capstone) + Cost & Usage Report
      → scripts/cost_query.py → dashboards/*.csv → matplotlib figures + Power BI
```

Region: **us-east-2** (resources). Cost Explorer is queried via its global **us-east-1** endpoint.

## Repo layout

| Path | Purpose | Phase |
|------|---------|-------|
| `src/train/` | Lahman → logistic-regression classifier → `model_params.json` | 1 ✅ in progress |
| `src/inference/` | Lambda handler (pure-numpy scoring) | 2 |
| `terraform/` | IaC: S3, IAM, Lambda, API Gateway, CloudWatch, Budget, CUR | 2–3 |
| `scripts/` | `load_test.py`, `cost_query.py`, `make_figures.py` | 3–5 |
| `dashboards/` | cost CSVs + matplotlib PNGs + Power BI exports | 5 |
| `.github/workflows/` | CI redeploy | 4 |

## Phase 1 — run the trainer (no AWS needed)

```bash
cd src/train
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
python train.py
```

Produces `model_params.json` (the tiny exported model the Lambda loads) and a local
`model.joblib`. Prints validation metrics — the model quality is only a sanity check.

## Safety

- **Serverless only** (no always-on resources); `terraform destroy` after collecting data.
- `$5` AWS Budget alarm; Free-Tier-scoped.
- **Never commit** AWS keys, account IDs, or `*.tfstate` (see `.gitignore`).

## Status

- [x] Phase 1 — trained + verified (2026-11-25; acc 0.861 / ROC-AUC 0.930; pure-numpy parity OK)
- [x] Phase 2 — **deployed** (live endpoint, 2026-11-25)
- [~] Phase 3 — scripts written; run load test + activate `Project` tag + wait 24–48h, then `cost_query.py`
- [~] Phase 4 — OIDC CI pipeline: `workflow_dispatch` (load-test / cost-query / all) + **daily cron that polls** for cost data (readiness-gated) and **opens a notification issue + uploads the artifact when it lands** — no stored keys, no manual approval
- [ ] Phase 5 — analysis, figures, write-up

Full plan: `Capstone-Build-Plan.md` in the Obsidian vault.
