# Pre-Sale Rights Valuation Pipeline

Predict the **realized resale price (KRW per ㎡)** of Korean pre-sale rights
(분양권) for **Seoul + Gyeonggi**, serve predictions via API + dashboard, and
orchestrate ingest → feature → train with Airflow. The deliverable is a clean,
reproducible, **leakage-free** ML pipeline — legibility over model surface area.

> Full plan & day-by-day sequencing: `presale_pipeline_2week_scope.md`.
> How-to-build rules for contributors: `CLAUDE.md`.

## Architecture

```
[MOLIT / ECOS / VWorld / Applyhome extractors]
        │  encoding auto-detect + retry + pydantic validation
        ▼
[DuckDB + Hive-partitioned Parquet raw layer]
        ▼
[Feature engineering → unified matrix]  (point-in-time correct)
        ▼
[LightGBM training] ──► [MLflow tracking + registry]
        │                        │
        ▼                        ▼
[Streamlit dashboard]     [FastAPI /predict + Docker]
```

Airflow orchestrates `extract → build_features → train` (retries + scheduled
backfill).

## Data sources

| Source | Role |
|---|---|
| MOLIT 분양권전매 실거래가 | **Training label + features** (resale price/㎡) |
| ECOS (Bank of Korea) | Macro features (base rate, mortgage yield, M2) |
| VWorld / Kakao Local | Geocode complexes; nearest-station distance |
| Applyhome (청약홈) | **Inference list only** — never enters training |

## Quickstart

```bash
make setup      # uv sync, init duckdb, copy .env.example -> .env
# fill in API keys in .env, and region lawd_codes in config/settings.yaml
make backfill   # historical ingest 2020 -> present
make features   # build unified feature matrix
make train      # time-split train + LightGBM + register to MLflow
make test       # pytest — includes leakage + time-split invariant tests
make up         # docker-compose: airflow + mlflow + fastapi + streamlit
```

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/). Fully local and
zero-cost — DuckDB + local Parquet + MLflow (SQLite). No cloud, no paid APIs.

## Results

_Reported on the held-out **time-based** test set (most recent slice)._

| Metric | Value |
|---|---|
| RMSE | _TBD_ |
| MAPE | _TBD_ |
| R² | _TBD_ |

Leakage audit: _TBD_ (see `tests/test_leakage.py`).

## Known Limitations

- **Label is realized resale price**, so predicted "premium" is market-relative,
  not fundamental value.
- **Regulatory regime not modeled** — 분양가상한제 / 전매제한 / 규제지역 status
  dominate premium mechanics and shift across 2020+ regimes; the training sample
  is selection-biased toward periods/areas where transfer was legal. A drift
  monitor won't catch a relationship that inverts when rules change.
- **Comps lagged ~30d** to reporting delay to avoid look-ahead.
- **Officetel/apartment pooling** adds noise (different tax/demand/usable-space);
  전용률 used to mitigate.
- **Single region** — not nationwide-generalizable as-is (region is a config
  value, not a rewrite).
