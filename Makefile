# serverless-ml-finops — one-command workflows.
# Override vars: make load PREDICTIONS=50000
API_URL     ?= https://7k2e5i5b24.execute-api.us-east-2.amazonaws.com/predict
PREDICTIONS ?= 20000

.PHONY: help train deploy load cost figures test fmt destroy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-9s\033[0m %s\n",$$1,$$2}'

train: ## Train the model → model_params.json (creates src/train/.venv)
	cd src/train && python3 -m venv .venv && ./.venv/bin/pip install -q -r requirements.txt && ./.venv/bin/python train.py

deploy: ## terraform init + apply
	cd terraform && terraform init && terraform apply

load: ## Generate inference load (PREDICTIONS=N)
	python3 scripts/load_test.py --url "$(API_URL)" -n $(PREDICTIONS)

cost: ## Query Cost Explorer → dashboards/*.csv
	pip install -q -r scripts/requirements.txt && python3 scripts/cost_query.py --predictions $(PREDICTIONS)

figures: ## Build matplotlib figures from the CSVs
	pip install -q matplotlib && python3 scripts/make_figures.py

test: ## Run unit tests
	pip install -q -r requirements-dev.txt && pytest -q

fmt: ## terraform fmt
	cd terraform && terraform fmt -recursive

destroy: ## Tear down all AWS resources
	cd terraform && terraform destroy
