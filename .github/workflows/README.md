# .github/workflows/ — Phase 4 (not yet built)

`deploy.yml` — on push, re-package the Lambda and run `terraform apply` (via GitHub
Actions OIDC to AWS — no long-lived keys in CI). This is the "MLOps discipline"
automation story and produces the second pipeline iteration used for the
cost-per-iteration comparison.
