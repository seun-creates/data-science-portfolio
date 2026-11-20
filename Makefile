# IMPORTANT: every indented line below must start with a real TAB, not spaces.
PY ?= python
export PYTHONPATH := projects/01-data-cleaning:projects/02-sales-etl:projects/03-churn-model:projects/04-demand-forecasting:projects/05-churn-api

.PHONY: help lint format typecheck security test cleaning etl churn forecast api docker-build docker-run all clean

help:
	@echo "make lint | format | typecheck | security | test"
	@echo "make cleaning | etl | churn | forecast | api | docker-build | docker-run | all | clean"

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy projects/01-data-cleaning/cleaning projects/02-sales-etl/etl projects/03-churn-model/churn projects/04-demand-forecasting/forecasting projects/05-churn-api/churn_api

security:
	bandit -q -r projects -x "*/tests/*"
	pip-audit -r requirements.txt

test:
	$(PY) -m pytest

cleaning:
	$(PY) -m cleaning.generate --out data/raw/customers_messy.csv
	$(PY) -m cleaning.cli data/raw/customers_messy.csv --out-dir data/clean

etl:
	$(PY) -m etl.generate --out data/raw/orders.jsonl
	$(PY) -m etl.cli load data/raw/orders.jsonl --db data/warehouse.db
	$(PY) -m etl.cli report --db data/warehouse.db

churn:
	$(PY) -m churn.train --out-dir artifacts/churn

forecast:
	$(PY) -m forecasting.backtest --out-dir artifacts/forecasting

api: churn
	set -a && . ./.env && set +a && CHURN_MODEL_DIR=artifacts/churn CHURN_API_DOCS=1 \
		$(PY) -m uvicorn churn_api.main:create_app --factory --host 127.0.0.1 --port 8000

docker-build:
	docker build -f projects/05-churn-api/Dockerfile -t churn-api:latest .

docker-run:
	docker run --rm -p 127.0.0.1:8000:8000 --env-file .env \
		--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
		--memory 512m --pids-limit 100 churn-api:latest

all: lint test cleaning etl churn forecast

clean:
	rm -rf data artifacts .pytest_cache .ruff_cache .mypy_cache
