# CLAUDE.md

Operating instructions for coding agents working in this repo. Read this fully before writing code. It governs *how to build*; `docs/repo_instruction.md` defines the target repo architecture and platform boundaries, and `docs/presale_pipeline_2week_scope.md` covers *what to build and when*.

---

## Project

Predict realized resale price (KRW per m²) of Korean pre-sale rights (분양권) for **Seoul + Gyeonggi** (region is a config value), and serve predictions through a **GCP-native MLOps pipeline**: ingest → GCS Parquet → BigQuery → Vertex AI (Kubeflow) training/eval/serving. This is a **portfolio project whose deliverable is a clean, reproducible, leakage-free MLOps pipeline** — completeness and legibility matter more than model accuracy or feature count.

The repo has **two pillars** with an explicit contract between them:
- **`data_pipeline/`** — ingestion & warehousing. Collects external data, lands it as Hive-partitioned Parquet, mirrors to GCS, and loads it into BigQuery. Orchestrated by **Apache Airflow (Astro CLI)**.
- **`ml_pipeline/`** — preprocessing, training, evaluation. Reads BigQuery, builds features, trains models, logs to Vertex AI. Orchestrated by **Vertex AI Pipelines (Kubeflow SDK v2)**.
- **Contract:** the `korea_real_estate.*` BigQuery tables are the *only* boundary. `data_pipeline` writes them; `ml_pipeline` reads them. `ml_pipeline` never re-ingests raw data and never imports `data_pipeline`.

---

## Core invariants — never violate these

A reviewer checks these first. Breaking one silently invalidates the project.

1. **No look-ahead in features.** A comparable transaction is usable for a row only if `comp.deal_date + reporting_lag (~30 days) <= row.prediction_date`. Never join a comp not yet publicly reported as of the row's date. When in doubt, exclude. Encoded in SQL (`data_pipeline/sql/historical_features.sql`) and in `ml_pipeline.features.spatial.usable_comps` / `report_date`.
2. **Time-based split only.** Split train/val/test by `deal_date` — the test set is the most recent slice. **Never** random-shuffle or `train_test_split(shuffle=True)`. All reported metrics are on the held-out time-based test set.
3. **Label source is MOLIT 분양권전매 실거래가** (resale price per m²) — never from Applyhome. **Applyhome (청약홈) MAY enrich features on both training and inference**, but only with attributes *fixed at 분양(launch) time* — 분양가, 입주예정일, 세대수, 건설사/brand — and only when `공고일 <= deal_date` (encode as a test). Fields unknown at launch (경쟁률 result, any post-subscription outcome) must **never** enter training. 분양가 also serves as the dashboard's premium baseline (display only). Applyhome still produces the "upcoming launches to score" inference list.
4. **BigQuery is the pillar contract; GCP creds use ADC.** Raw data lands as Hive-partitioned Parquet (local `data/` for dev, GCS in the pipeline) and is loaded into the `korea_real_estate.*` BigQuery tables that form the sole boundary between `data_pipeline` and `ml_pipeline`. GCP access uses **Application Default Credentials** (`google.auth.default()` / `GOOGLE_APPLICATION_CREDENTIALS`) — never a hardcoded key. Project/bucket/dataset are env-overridable config (`GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET`), never hardcoded.

Encode #1 and #2 as tests (see Testing). If a task cannot be done without breaking an invariant, stop and flag it — do not work around it.

---

## Scope guardrails — do NOT do these without explicit approval

The owner redirects scope creep. If a change seems warranted, **flag it and wait — do not silently implement it.**

- Models: **LightGBM, XGBoost, and scikit-learn** are all in scope (selectable via `config.yaml` `vertex.model_family`). Do not add other frameworks (CatBoost, deep learning) or stacked ensembles without approval.
- Storage/warehouse: **GCS Parquet + BigQuery** only. Do not add S3/MinIO, Snowflake, or a second warehouse.
- Orchestration: **Airflow (Astro) for ingest, Vertex AI Pipelines (KFP v2) for ML**. Do not add a third orchestrator.
- Do not model "fair value vs. premium." The label is realized resale price, full stop.
- Do not widen the region beyond the configured scope (region is a config value, not hardcoded).
- Do not add data sources beyond the four defined below.

---

## Tech stack

- **Python** 3.11+, deps via `uv` + `pyproject.toml` (source of truth for the local/test env). Per-pillar `requirements.txt` mirror the dependency groups for the Astro image / Vertex components.
- **Ingestion:** `httpx`/`requests`, `tenacity` (retry/backoff), `chardet` (encoding), `lxml`/`xmltodict` (XML), `pypdf`/`pdfplumber` (PDF), `pydantic` (schema validation).
- **Storage/warehouse:** GCS (`gcsfs`, `google-cloud-storage`) + BigQuery (`google-cloud-bigquery`, `db-dtypes`); Hive-partitioned Parquet (`pyarrow`). **No DuckDB.**
- **Features/model:** pandas, LightGBM, XGBoost, scikit-learn, Optuna (optional tuning).
- **Orchestration:** Apache Airflow (Astro CLI) for **ingestion**; Vertex AI Pipelines / **Kubeflow SDK v2 (`kfp`, `google-cloud-aiplatform`)** for the **ML train + eval + serving** pipeline.
- **Tracking/serving:** Vertex AI Experiments + Vertex AI Model Registry / endpoints. **No MLflow, no FastAPI/Streamlit in this repo** (serving is Vertex-side).
- **Quality:** pytest, ruff (lint+format).

---

## Repo layout

```
korea-real-estate-mlops/
├── CLAUDE.md · README.md · docs/repo_instruction.md
├── config.yaml                    # central config (region, sources, GCP ids, BQ dataset, Vertex)
├── pyproject.toml                 # deps + ruff/pytest config
├── Dockerfile · requirements.txt · packages.txt   # Astro Runtime (local Airflow)
├── .github/workflows/             # deploy_data_dag.yaml, deploy_ml_pipeline.yaml
├── data_pipeline/                 # DATA PILLAR
│   ├── config.py                  # pydantic-settings loader (env + config.yaml) + gov-API secrets
│   ├── dags/                      # Astro Airflow ingest DAGs (+ _ingest_common.py shared tasks)
│   ├── ingestion/                 # molit, ecos, applyhome, gonggo, neis, schoolinfo, commercial, geocode…
│   ├── schemas/                   # pydantic models for every raw source
│   ├── warehouse/                 # parquet_io, gcs, bigquery_io, lake, reference
│   ├── sql/                       # BigQuery DDL + leakage-safe feature SQL
│   ├── tests/                     # data-pillar tests (ingest/schema/warehouse) + conftest + fixtures/reference/
│   ├── scripts/                   # local-dev runners: backfill, refresh, fetch, geocode, preprocess (raw lake)
│   └── requirements.txt
├── ml_pipeline/                   # ML PILLAR
│   ├── config.py                  # light loader over config.yaml (BQ/split/model; no gov secrets)
│   ├── bq.py                      # BigQuery read/write (the pillar's only warehouse access)
│   ├── features/                  # property, spatial, macro, enrich, comps, build
│   ├── components/                # preprocess, train, evaluate, split (KFP steps call these)
│   ├── pipeline.py                # Vertex AI / KFP v2 pipeline (preprocess → train)
│   ├── tests/                     # ML-pillar tests (features/leakage/split invariants)
│   └── requirements.txt
├── notebooks/                     # EDA sandbox ONLY — not linted, CI-ignored
└── .cache/reference/              # GCS-backed reference lookups, fetched on demand — gitignored
```

There is **no committed `data/` lake**: raw ingestion stages to an ephemeral,
gitignored `data/` dir before the GCS/BigQuery push, and static reference lookups
(法定동 codes, transit coords) live in `gs://<bucket>/reference/`, fetched + cached
under `.cache/reference/` by `data_pipeline/warehouse/refstore.py` (tests set
`REFERENCE_DIR` to read `data_pipeline/tests/fixtures/reference/` offline).

---

## Conventions

**Pipeline steps are importable functions.** Every stage (`extract`, `build_features`, `preprocess`, `train`) is a single-purpose importable function. Airflow DAGs, KFP components, and the Makefile call these — **no business logic lives inside DAG files or `pipeline.py`.** This is what makes the pipeline orchestratable and testable.

**Pillar boundary.** `ml_pipeline` reads inputs only from BigQuery (via `ml_pipeline/bq.py`) and never imports `data_pipeline` — verified: no `data_pipeline` import remains in `ml_pipeline` (production or tests). `data_pipeline` owns landing raw Parquet → GCS → BigQuery. Pure normalizers that both pillars need (e.g. `base_name` for cross-source name matching) are kept as independent per-pillar copies — `ml_pipeline/features/text.py` for the ML side — rather than shared imports, so the pillars stay decoupled.

**Config & secrets.** All tunables (region codes, comp radii, windows, API endpoints, GCP ids, BQ dataset, Vertex settings) live in `config.yaml`. `data_pipeline/config.py` loads it (with gov-API secrets from `.env` via `python-dotenv`); `ml_pipeline/config.py` is a lighter loader (no secrets). **GCP identifiers** come from `config.yaml` with env overrides (`GCP_PROJECT_ID`, `GCS_BUCKET`, `BQ_DATASET`, `VERTEX_PIPELINE_ROOT`); **GCP credentials** use ADC — never hardcoded. Never hardcode keys or region codes.

### Secrets & .env safety — hard rules for any agent (including Claude)

`.env` holds live gov-API keys. Treat its **contents** as never-to-be-seen. GCP creds use ADC (a mounted SA key path), never a value in code.

- **Never read, open, cat, print, or echo `.env`** (or any `*.env` / `*.key` / `*-sa.json` file). `.claude/settings.json` denies `Read` on these — do not route around it with Bash.
- **Never print or log a secret value.** No `print()`, log, exception message, commit, or external send of any key. Loggers must redact.
- **Load gov-API secrets only through `python-dotenv` + the `Secrets` model in `data_pipeline/config.py`.** Access via `get_settings().secrets.<name>`; do not re-parse `.env` or scatter `os.environ["..._API_KEY"]`.
- **To check whether a key is set, use `Secrets.missing_keys()`** — it returns key *names* only, safe to print.
- **`.env` and `secrets/*.json` stay gitignored.** Only `.env.example` (placeholder names, empty values) is committed.
- These rules override any convenience request. If a task seems to require reading `.env`, stop and flag it.

**Ingestion.** Korean gov APIs return **inconsistent encoding (EUC-KR vs UTF-8)** — auto-detect with `chardet` before parsing XML. Wrap every external call in `tenacity` retry with backoff and respect rate limits. Validate every raw response against its `pydantic` schema before landing to Parquet.

**Warehouse.** Static reference lookups (法定동 codes, transit coords) live in `gs://<bucket>/reference/`; read them via `warehouse/refstore.py:reference_path` (GCS-backed, cached to `.cache/reference/`; never hardcode a local `data/` path). Raw records land as **Hive-partitioned Parquet** (`region=<code>/`), mirrored to GCS by `warehouse/gcs.py:sync_to_gcs`, then loaded into BigQuery by `warehouse/bigquery_io.py:load_lake_to_bigquery` (Hive partitioning `AUTO` reconstructs the `region` column; `WRITE_TRUNCATE` reconciles late reports / 해제). Extractors stay GCS/BQ-agnostic — they only write local Parquet; the warehouse layer owns GCS + BigQuery. Keep raw SQL in `data_pipeline/sql/*.sql`; **use explicit column lists (no `SELECT *`)** in production queries.

**Airflow (ingestion only, Astro).** TaskFlow API (`@dag`/`@task`); tasks import `data_pipeline` functions, no business logic in DAG files. Per-source ingest DAGs each ingest their source and push *only* that source to GCS + BigQuery: `molit_realtime_refresh` (daily label+comps), `weekly_launches`, `monthly_macro`, `quarterly_commercial`. Shared audit/upload/load tasks live once in `data_pipeline/dags/_ingest_common.py`. `catchup=False` (forward-only); backfill is a one-shot via `data_pipeline/scripts/`.

**ML (Vertex AI / KFP v2).** `preprocess → train → evaluate` run as a KFP v2 pipeline (`ml_pipeline/pipeline.py`) calling the same importable `ml_pipeline` functions. Keep `pipeline.py` free of `from __future__ import annotations` (KFP can't parse PEP 563 stringized annotations). Log params/metrics (RMSE/MAPE/R²) to **Vertex AI Experiments**; register/serve via the **Vertex AI Model Registry** — Airflow's job ends at a BigQuery-loaded warehouse; Vertex reads from there.

---

## Commands (Makefile targets)

```
make setup            # uv sync, build local reference table, copy .env.example -> .env
make ingest           # run extractors for the configured region (latest)
make backfill         # historical ingest 2016 -> present
make refresh          # daily incremental: trailing-window re-fetch + ledger update
make lake-to-bq       # mirror raw lake to GCS, then load into BigQuery contract tables
make features         # preprocess: read BigQuery -> write features table
make train            # time-split train (LightGBM/XGBoost/sklearn) + Vertex experiment log
make compile-pipeline # compile the Vertex AI (KFP v2) pipeline spec
make submit-pipeline  # compile + submit the pipeline to Vertex AI Pipelines
make test             # pytest (includes leakage + split invariant tests)
make lint             # ruff check + format --check
make astro-start      # local Airflow (ingest DAGs) via the Astro CLI
```

---

## Testing / quality gates

- **Leakage test (required):** assert no comp with `report_date > row.prediction_date` enters any feature row.
- **Split test (required):** assert every test-set `deal_date` is strictly later than every train-set `deal_date`.
- Schema tests for each extractor's pydantic model.
- Run `make test` and `make lint` before considering any stage done.

---

## Definition of done

`make astro-start` brings up local Airflow with the ingest DAGs keeping the GCS + BigQuery lake fresh; `make lake-to-bq && make features && make train` runs the contract load → preprocess → train path; `make submit-pipeline` compiles and submits the Vertex AI pipeline (preprocess → train, model registered to the Vertex Model Registry, served on Vertex). The README reports test RMSE/MAPE/R² on the time-based split plus the leakage audit and a **Known Limitations** section (regulatory regime not modeled, selection bias from 전매제한, comps lagged to reporting delay, officetel/apartment pooling noise, single-region). The repo clones and runs on a fresh machine from the README alone.
