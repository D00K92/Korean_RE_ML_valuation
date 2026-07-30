.PHONY: setup ingest backfill refresh features train test lint up down

setup:            ## install deps, init duckdb, copy .env.example -> .env
	uv sync
	@test -f .env || cp .env.example .env
	uv run python -c "from presale.storage.duckdb_io import init_db; init_db()"

ingest:           ## run extractors for the configured region (latest)
	uv run python -m presale.extract.molit --mode latest

backfill:         ## historical ingest 2020 -> present
	uv run python -m presale.extract.molit --mode backfill

refresh:          ## daily incremental: re-fetch trailing window + update ledger
	uv run python scripts/refresh_realtime.py

features:         ## build unified feature matrix
	uv run python -m presale.features.build

train:            ## time-split train + LightGBM + log/register to MLflow
	uv run python -m presale.train.model

test:             ## pytest (includes leakage + split invariant tests)
	uv run pytest -q

lint:             ## ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

up:               ## docker-compose up: airflow + mlflow + fastapi + streamlit
	docker compose up --build

down:
	docker compose down
