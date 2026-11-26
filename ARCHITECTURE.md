# Architecture & Design Decisions

This document explains *why* the pipeline is built the way it is — the trade-offs behind the
serverless design, the FinOps measurement approach, and the operational instrumentation. For *how*
to run it, see the [README](README.md).

## Table of Contents

- [The research question](#the-research-question)
- [System design](#system-design)
- [Key design decisions](#key-design-decisions)
- [The FinOps narrative](#the-finops-narrative)
- [Observability](#observability)
- [Security posture](#security-posture)
- [Limitations & future work](#limitations--future-work)

---

## The research question

> **What does it cost to serve a machine-learning model on a serverless AWS stack, and how is that
> cost distributed across services?**

The model itself is intentionally trivial — a logistic-regression Hall-of-Fame classifier. Holding
the model constant keeps the study focused on the **serving pipeline's cost and operations**, which is
where the Cloud Engineering value lies. A "better" model would change nothing about the cost structure
this project measures.

---

## System design

A request path with no always-on compute:

```
Client → API Gateway (HTTP API) → Lambda (hof-inference) → JSON response
```

Supporting infrastructure, all Terraform-managed and tagged `Project=capstone`:

- **S3** (versioned) — stores the model artifact; versioning supports the MLOps "model lineage" story.
- **CloudWatch** — log group (14-day retention), a dashboard, and saved Logs Insights queries.
- **IAM** — a least-privilege Lambda execution role and a GitHub OIDC role for CI.
- **Cost Explorer + a cost-allocation tag** — the FinOps measurement surface.

---

## Key design decisions

### Pure-Python inference (no ML libraries at runtime)

Packaging scikit-learn/numpy into a Lambda is the classic serverless-ML pain point (layer size,
cold-start weight, build complexity). Instead, training exports just the model's coefficients, scaler
mean/scale, and intercept to `model_params.json`. The Lambda re-implements scoring in ~10 lines of
standard-library Python:

```
p = sigmoid( Σ coefᵢ · (xᵢ − meanᵢ) / scaleᵢ  +  intercept )
```

**Trade-off:** this only works for models reducible to a small parameter set (linear/logistic models,
small trees). For a deep net you'd accept a container image or a layer. For this workload it means a
**2-file deployment package, no layer, minimal cold start** — and a unit test asserts the pure-Python
path matches the scikit-learn pipeline to 1e-5, so the shortcut is provably equivalent.

### Serverless over a container/instance

API Gateway + Lambda means **zero cost at idle** and no capacity to manage — the right default for
spiky, low-volume inference. The trade-off is per-request latency (cold starts) and a per-request
pricing model, both of which this project *measures* rather than assumes.

### Cost Explorer over CUR

The Cost and Usage Report (CUR) is higher fidelity but requires an S3 bucket with a specific policy, a
`us-east-1`-pinned provider, and a delivery lag. Cost Explorer's `GetCostAndUsage` API — filtered by the
`Project` tag, grouped by `SERVICE` + `USAGE_TYPE` — is sufficient for per-service and per-1,000-prediction
figures with far less setup. CUR remains the backstop if line-item fidelity is ever needed.

### Terraform for everything

The entire stack is `apply`/`destroy`-able. This is both good hygiene (nothing lingers to bill) and
part of the thesis: **reproducible-from-code** infrastructure is what lets the cost measurement be
re-run and trusted.

### OIDC for CI → AWS

GitHub Actions assumes a scoped IAM role via web-identity federation — **no long-lived access keys**
stored as secrets. The CI role grants only Cost Explorer read and `cloudwatch:GetMetricData`.

---

## The FinOps narrative

The most interesting finding is a FinOps lesson, not an engineering one:

**Free Tier usually drives the *actual* bill to \$0**, which makes the raw invoice useless as a cost
signal. A naive "it cost nothing" conclusion hides the real economics. So the pipeline reports two numbers:

1. **Actual billed cost** — what Cost Explorer shows (often \$0 under Free Tier). Honest, but uninformative at this scale.
2. **List-price cost per 1,000 predictions** — the marginal cost if this ran *outside* Free Tier, computed from published per-unit prices applied to the measured usage.

The list-price unit cost is the headline because it's the number that generalizes — it tells you what
the pipeline would cost at scale. At serverless volumes the per-prediction cost is **request-dominated**
(API Gateway + Lambda invocation charges), sub-cent, and effectively flat per request — a finding you
can only state credibly by measuring usage and pricing it explicitly, rather than reading a \$0 invoice.

The planned **Lambda memory experiment** (128 / 256 / 512 MB) extends this: more memory cuts duration
but raises the GB-ms rate, so there's a cost/latency sweet spot the pipeline can find empirically.

---

## Observability

Operational instrumentation, defined in `terraform/observability.tf`:

- **Structured JSON logging** — one line per invocation (`event, request_id, cold_start, latency_ms,
  prediction, hof_probability, status`). CloudWatch Logs Insights auto-discovers the fields, so latency
  percentiles and prediction distributions are queryable without a parse step.
- **CloudWatch dashboard** (`capstone-mlfinops`) — one pane: invocations/errors/throttles, Duration
  percentiles, concurrency, and the API Gateway request/latency/error metrics.
- **Saved Logs Insights queries** — latency-by-cold-start, predictions-breakdown, recent-errors.
- **In-pipeline metrics** — the CI `load-test` action pulls the same metrics via `GetMetricData` and
  writes them to the Actions job summary, so the pipeline reports its own health.

This maps directly to real-world ops practice: dashboards for the at-a-glance view, structured logs for
drill-down, and metrics surfaced where the work happens (the CI run) instead of only in a console.

---

## Security posture

- **No stored cloud credentials in CI** — OIDC web-identity federation; the role trust is scoped to this repo.
- **Least privilege** — the CI role is read-only (Cost Explorer + CloudWatch metrics); the Lambda role is `AWSLambdaBasicExecutionRole` only.
- **Secrets hygiene** — `*.tfstate`, `*.tfvars`, `.env`, keys, and the trained `*.joblib` are gitignored; only the parameter JSON is committed.
- **Cost guardrail** — a \$5 AWS Budget alarm bounds blast radius.

**Known gap (Tier-3 future work):** the *deploy* identity is still a local admin key. A production setup
would replace it with a least-privilege deploy role and move Terraform state to a remote backend (S3 + DynamoDB lock).

---

## Limitations & future work

- **Billing latency (24–48h)** drives the whole schedule — cost can't be read in the same run that
  generates load; the pipeline polls and notifies instead.
- **Free Tier masks the real bill** — mitigated via list-price unit cost (see above).
- **Single-region, single-function** — no multi-region or canary story; out of scope for a cost study.
- **Future work:** the memory/cost experiment; remote Terraform state; a least-privilege deploy role;
  X-Ray tracing for per-request spans; a published static cost report.
