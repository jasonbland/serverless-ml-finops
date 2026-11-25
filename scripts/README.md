# scripts/ — Phase 3–5 (not yet built)

- `load_test.py` — generate a controlled, repeatable volume of inference requests.
- `cost_query.py` — pull Cost Explorer / CUR data **filtered by the `Project=capstone`
  tag** (Cost Explorer client pinned to `us-east-1`), normalize to cost per 1,000
  predictions + per-service breakdown, write `dashboards/*.csv`.
- `make_figures.py` — turn the CSVs into committed **matplotlib** PNG charts
  (reproducible-from-code; Power BI is the separate manual presentation layer).
