.PHONY: setup ingest backfill refresh lake-to-bq features train \
        compile-pipeline submit-pipeline test lint astro-start astro-stop

setup:            ## install deps, cache GCS reference lookups, copy .env.example -> .env
	uv sync
	@test -f .env || cp .env.example .env
	uv run python -c "from data_pipeline.warehouse.parquet_io import init_db; init_db()"

ingest:           ## run extractors for the configured region (latest)
	uv run python -m data_pipeline.ingestion.molit --mode latest

backfill:         ## historical ingest 2016 -> present
	uv run python -m data_pipeline.ingestion.molit --mode backfill

refresh:          ## daily incremental: re-fetch trailing window + update ledger
	uv run python data_pipeline/scripts/refresh.py

lake-to-bq:       ## mirror the raw lake to GCS, then load it into BigQuery contract tables
	uv run python -c "from data_pipeline.warehouse.gcs import sync_to_gcs; sync_to_gcs()"
	uv run python -c "from data_pipeline.warehouse.bigquery_io import load_lake_to_bigquery; \
	  import sys; print(load_lake_to_bigquery(['molit_resale','molit_apt_trade','ecos_macro','applyhome','commercial']))"

features:         ## preprocess: read BigQuery contract tables -> write features table
	uv run python -m ml_pipeline.components.preprocess

train:            ## time-split train (LightGBM/XGBoost/sklearn) + Vertex experiment log
	uv run python -m ml_pipeline.components.train

compile-pipeline: ## compile the Vertex AI (KFP v2) pipeline spec
	uv run --group ml python -m ml_pipeline.pipeline

submit-pipeline:  ## compile + submit the pipeline to Vertex AI Pipelines
	uv run --group ml python -c "from ml_pipeline.pipeline import submit; print(submit())"

test:             ## pytest (includes leakage + split invariant tests)
	uv run pytest -q

lint:             ## ruff lint + format check
	uv run ruff check .
	uv run ruff format --check .

astro-start:      ## local Airflow (ingest DAGs) via the Astro CLI
	astro dev start

astro-stop:
	astro dev stop
