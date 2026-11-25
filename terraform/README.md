# terraform/ — Phase 2–3 (not yet built)

Infrastructure as code for the serverless pipeline:
- `main.tf` — S3 (data + model), IAM (least-privilege Lambda role), Lambda, API Gateway
  HTTP API, CloudWatch log group, AWS Budget, Cost & Usage Report + its bucket.
- `variables.tf` — `region = us-east-2`, project tag, budget amount.
- `outputs.tf` — the API Gateway invoke URL.

Every resource carries `tags = { Project = "capstone" }` for cost attribution.
State stays local and **gitignored** (`*.tfstate`).
