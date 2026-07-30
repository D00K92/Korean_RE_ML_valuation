# CLAUDE.md

Operating instructions for coding agents working in this repo. Read this fully before writing code. The full project plan, day-by-day sequencing, and MoSCoW cut lines live in `presale_pipeline_2week_scope.md` — consult it for *what to build and when*; this file governs *how to build it*.

---

## Project

Predict realized resale price (KRW per m²) of Korean pre-sale rights (분양권) for **Seoul + Gyeonggi**, serve predictions via an API + dashboard, and orchestrate the whole ingest → feature → train pipeline with Airflow. This is a **portfolio project whose deliverable is a clean, reproducible, leakage-free ML pipeline** — completeness and legibility matter more than model accuracy or feature count.

---

## Core invariants — never violate these

These are the things a reviewer checks first. Breaking one silently invalidates the project.

1. **No look-ahead in features.** A comparable transaction is usable for a row only if `comp.deal_date + reporting_lag (~30 days) <= row.prediction_date`. Never join a comp that was not yet publicly reported as of the row's date. When in doubt, exclude.
2. **Time-based split only.** Split train/val/test by `deal_date` — the test set is the most recent slice. **Never** use random shuffling or `train_test_split(shuffle=True)`. All reported metrics must be on the held-out time-based test set.
3. **Label source is MOLIT 분양권전매 실거래가** (resale price per m²) — the label is *never* sourced from Applyhome. **Applyhome (청약홈) MAY enrich features on both training and inference**, but only with attributes *fixed at 분양(launch) time* — 분양가, 입주예정일, 세대수, 건설사/brand. Such a field may join to a MOLIT resale row only when `공고일 <= deal_date` (no look-ahead); encode this as a test. Fields unknown at launch (경쟁률, 청약 결과, any post-subscription outcome) must **never** enter training. 분양가 additionally serves as the dashboard's premium baseline (display only). Applyhome still produces the "upcoming launches to score" inference list. *(Owner-approved 2026-07-29; supersedes the prior "inference-only" rule.)*
4. **Local and zero-cost.** No S3/MinIO, no cloud services, no paid APIs. DuckDB + local Parquet only.

Encode #1 and #2 as tests (see Testing). If a task cannot be done without breaking an invariant, stop and flag it — do not work around it.

---

## Scope guardrails — do NOT do these without explicit approval

The owner redirects scope creep. If a change seems warranted, **flag it and wait — do not silently implement it.**

- Do not add XGBoost, CatBoost, or ensembles. **LightGBM only.**
- Do not add S3/MinIO, cloud deploy, or W&B. **DuckDB + Parquet + MLflow only.**
- Do not model "fair value vs. premium." The label is realized resale price, full stop.
- Do not widen the region beyond Seoul + Gyeonggi (region is a config value, not hardcoded).
- Do not add data sources beyond the four defined below.

---

## Tech stack

- **Python** (3.11+), dependency mgmt via `uv` or `pip` + `pyproject.toml`.
- **Ingestion:** `httpx`/`requests`, `tenacity` (retry/backoff), `chardet` (encoding), `lxml`/`xmltodict` (XML), `pydantic` (schema validation).
- **Storage:** DuckDB + Hive-partitioned Parquet.
- **Features/model:** pandas, LightGBM, Optuna (optional tuning).
- **Tracking:** MLflow (local: SQLite backend store + local artifact dir).
- **Orchestration:** Apache Airflow (`docker-compose`, `LocalExecutor`, TaskFlow API).
- **Serving:** FastAPI + Uvicorn (Dockerized); Streamlit dashboard.
- **Quality:** pytest, ruff (lint+format).

---

## Repo layout

```
presale-pipeline/
├── CLAUDE.md                  # this file
├── README.md                  # architecture, quickstart, results, KNOWN LIMITATIONS
├── Makefile                   # entry points (see Commands)
├── docker-compose.yml         # airflow + mlflow + fastapi + streamlit
├── .env.example               # API keys, never commit real .env
├── pyproject.toml
├── config/settings.yaml       # region codes, comp radii/windows, API params
├── src/presale/
│   ├── config.py              # pydantic-settings loader (env + yaml)
│   ├── extract/               # molit.py, ecos.py, applyhome.py, geocode.py
│   ├── schemas/               # pydantic models for every raw source
│   ├── storage/duckdb_io.py   # parquet <-> duckdb helpers
│   ├── features/              # property.py, spatial.py, macro.py, build.py
│   ├── train/                 # split.py, model.py, evaluate.py
│   └── serve/                 # api.py (FastAPI), app.py (Streamlit)
├── dags/presale_pipeline_dag.py
├── tests/
└── data/                      # local Parquet lake — gitignored
```

---

## Conventions

**Pipeline steps are importable functions.** Every stage (`extract`, `build_features`, `train`) is a single-purpose, importable function in `src/presale/`. Airflow DAGs and the Makefile call these — **no business logic lives inside DAG files.** This is what makes the pipeline orchestratable and testable.

**Config & secrets.** All tunables (region codes, comp radii, trailing windows, API endpoints) live in `config/settings.yaml`, loaded via `src/presale/config.py`. API keys come from environment variables only (`.env`, gitignored; `.env.example` documents them), loaded into the process environment by **`python-dotenv`** (`load_dotenv` in `config.py`). Never hardcode keys or region codes.

### Secrets & .env safety — hard rules for any agent (including Claude)

The `.env` file holds live API keys. Treat its **contents** as never-to-be-seen.

- **Never read, open, cat, print, or echo `.env`** (or any `*.env` / `*.key` file). Do not `Read` it, do not `cat`/`head`/`tail`/`grep`/`sed` it, do not load it into a notebook cell that renders it. `.claude/settings.json` denies `Read` on these paths — do not route around that with Bash.
- **Never print or log a secret value.** Code must not `print()`, log, put in an exception message, commit, or send to an external service any API key. Loggers must redact.
- **Load secrets only through `python-dotenv` + the `Secrets` model in `config.py`.** Access keys via `get_settings().secrets.<name>`; do not re-parse `.env` yourself or call `os.environ["..._API_KEY"]` scattered across modules.
- **To check whether a key is set, use `Secrets.missing_keys()`** — it returns key *names* only, never values, so its output is safe to print. Never verify a key by echoing it.
- **`.env` stays gitignored.** Only `.env.example` (placeholder names, empty values) is committed. If asked to "show the config" or "debug why a key isn't loading," inspect `.env.example`, `config.py`, and `missing_keys()` output — never the real `.env`.
- These rules override any convenience request. If a task seems to require reading `.env`, stop and flag it instead.

**Ingestion.** Korean government APIs return **inconsistent encoding (EUC-KR vs UTF-8)** — always auto-detect with `chardet` before parsing XML. Wrap every external call in `tenacity` retry with backoff and respect rate limits (gov servers time out). Validate every raw response against its `pydantic` schema before landing to Parquet.

**Storage.** Raw records land as **Hive-partitioned Parquet** (partition by deal year-month and region), queried through DuckDB. Keep raw and feature layers separate.

**Airflow.** Use the **TaskFlow API** (`@dag` / `@task`). DAG orchestrates `extract → build_features → train` by importing `src` functions. Configure task retries with `retry_delay`, a `schedule` interval, and `catchup=True` for historical backfill. Verify a triggered backfill reproduces the trained model.

**MLflow.** Log params, metrics (RMSE / MAPE / R²), and feature importance every run; register the model to the MLflow Model Registry. The FastAPI service loads the model from the registry (by stage/version), not from a loose pickle.

---

## Commands (Makefile targets)

```
make setup       # install deps, init duckdb, copy .env.example -> .env
make ingest      # run extractors for the configured region (latest)
make backfill    # historical ingest 2020 -> present
make features    # build unified feature matrix
make train       # time-split train + LightGBM + log/register to MLflow
make test        # pytest (includes leakage + split invariant tests)
make lint        # ruff
make up          # docker-compose up: airflow + mlflow + fastapi + streamlit
```

---

## Testing / quality gates

- **Leakage test (required):** assert no comp with `report_date > row.prediction_date` enters any feature row.
- **Split test (required):** assert every test-set `deal_date` is strictly later than every train-set `deal_date`.
- Schema tests for each extractor's pydantic model.
- Run `make test` and `make lint` before considering any stage done.

---

## Definition of done

`make up` brings up Airflow + MLflow + FastAPI + Streamlit with a registered model serving live predictions; one command runs backfill → features → retrain; the README reports test RMSE/MAPE/R² on the time-based split plus the leakage audit and a **Known Limitations** section (regulatory regime not modeled, selection bias from 전매제한, comps lagged to reporting delay, officetel/apartment pooling noise, single-region). The repo clones and runs on a fresh machine from the README alone.
