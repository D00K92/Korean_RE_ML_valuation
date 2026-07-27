# Pre-Sale Rights Valuation Pipeline — 2-Week Scoped Build

**Purpose of this project:** Demonstrate end-to-end capability — messy real-world data management → feature engineering → ML training → registry → containerized serving + monitoring. The domain (Korean pre-sale rights) is the vehicle; the *deliverable being evaluated* is a clean, reproducible, self-aware ML pipeline. Optimize for **completeness and legibility over surface area**.

---

## 1. Scope Decisions vs. Original

| Original | 2-Week Version | Why |
|---|---|---|
| Nationwide | **Seoul + Gyeonggi cluster** | Volume + spatial-join tractability; parameterize region so nationwide is a config change, not a rewrite. Note: Seoul 분양권 volume is thinner (tighter 전매제한) — the Gyeonggi cluster carries the sample |
| 4 primary + 2 spatial APIs | **2 primary** (MOLIT resale, Applyhome) + **2 supporting** (ECOS macro, VWorld/Kakao geocode) | MOLIT resale = training label; Applyhome = inference list only |
| Predict fair value V, derive premium | **Predict realized resale price directly** | Removes the hardest modeling problem (fundamental value ≠ market price); every pipeline stage stays intact |
| S3/MinIO + Airflow + MLflow + Evidently + FastAPI + Streamlit + Docker | **DuckDB + Parquet, LightGBM, MLflow, Airflow, FastAPI + Streamlit, Docker**; Evidently optional | Local + free = zero cost. **Airflow is now a Must** (explicit learning goal); drop S3/MinIO and Evidently to make room |
| LightGBM + XGBoost + CatBoost | **LightGBM only** | One model, tuned and evaluated properly, beats three half-done |

**Key reframe:** Training runs entirely on **MOLIT 분양권전매 실거래가** (label = resale price per m²; features = property + spatial + macro + timing). This sidesteps the fuzzy subscription→resale join. Applyhome data is only ingested to produce the *"upcoming launches to score"* list for the dashboard.

**Volume fallback (validate Day 1):** If 분양권 resale volume in the chosen region is too thin to train, switch the label to regular apartment/officetel **매매 실거래가** — identical pipeline, higher volume, the trading framing weakens to a README footnote.

---

## 2. Data Sources

| Source | Role | Notes |
|---|---|---|
| MOLIT 분양권전매 실거래가 API | **Training label + features** | EUC-KR/UTF-8 auto-detect, XML parse, rate-limit + retry, backfill 2020→present |
| ECOS (Bank of Korea) | Macro features | Base rate, mortgage yield, M2 growth, sentiment — monthly |
| VWorld / Kakao Local | Geocode complexes; nearest-station distance | Download static subway-station coordinates once |
| Applyhome (청약홈) | **Inference list only** | Upcoming launches with base price + area to score in the dashboard |

---

## 3. Feature Set (trimmed)

- **Property:** exclusive area, floor, building age, 전용률 (usable-space ratio), log(total units), developer tier (Top-10 brand vs regional).
- **Spatial:** weighted avg comp price per m² within 500m / 1km / 3km over trailing 30/60/90d; straight-line distance to nearest station. **Dynamic radius expansion** for sparse areas (500m → 1km → 3km → district).
- **Macro/temporal:** 6-month base-rate delta, months-to-completion.

**Non-negotiable — point-in-time correctness:** a comp is only usable if `deal_date + reporting_lag (~30d) ≤ prediction_date`. Building this correctly is the single highest-signal thing in the project. A reviewer checks for exactly this.

---

## 4. Architecture

```
[MOLIT/ECOS/VWorld/Applyhome extractors]
        │  (encoding + retry + Pydantic validation)
        ▼
[DuckDB + Hive-partitioned Parquet raw layer]
        │
        ▼
[Feature engineering → unified matrix]
        │
        ▼
[LightGBM training]──►[MLflow tracking + registry]
        │                        │
   [Evidently drift]        [FastAPI /predict + Docker]
                                 │
                          [Streamlit: rank upcoming launches by premium]
```

**Airflow DAG orchestrates ingest → FE → train** (retries + scheduled backfill) — core to this build, not optional.

---

## 5. Day-by-Day Plan (~14 intense days)

### Week 1 — Data & Features (the "data management" proof)
- **Day 1** — Repo scaffold, config, secret handling. MOLIT extractor: pagination, encoding auto-detect, XML→DataFrame, `tenacity` retry, rate limit. Land Hive-partitioned Parquet. Pydantic schema. **Validate region volume (Seoul + Gyeonggi); commit region.** From the start, write each pipeline step (extract, feature-build, train) as an importable, single-purpose function/module — this makes wrapping them as Airflow tasks on Days 9–10 trivial instead of a refactor.
- **Day 2** — Backfill 2020→present. ECOS macro extractor → monthly table. Data-quality checks (nulls, dtypes, dedupe).
- **Day 3** — Geocode complexes (VWorld/Kakao); nearest-station distances from static station coords. Applyhome extractor for the inference list.
- **Day 4** — Feature engineering pt.1: property features, macro joins (6m rate delta), time-to-completion.
- **Day 5** — Feature engineering pt.2: spatial comps at 3 radii × 3 windows **with point-in-time filter**; dynamic radius expansion.
- **Day 6** — Assemble unified matrix in DuckDB. Leakage audit + EDA sanity plots. Buffer.

### Week 2 — ML, MLOps, Serving
- **Day 7** — Training pipeline: **time-based** train/val/test split (split by deal_date, no random shuffle). LightGBM baseline. RMSE / MAPE / R². Feature importance.
- **Day 8** — MLflow: log params/metrics/artifacts, register + version model. Optuna tuning (time-boxed). Error stratification by region / price band.
- **Day 9** — Airflow setup + fundamentals (learning day). Official `docker-compose`, `LocalExecutor`, SQLite/Postgres metadata DB. Write one DAG using the **TaskFlow API** (`@dag`/`@task`) wrapping the importable functions from Day 1: `extract → feature_build → train`. Get it running manually once end-to-end.
- **Day 10** — Airflow hardening: task retries + `retry_delay`, `schedule` interval, `catchup`/backfill over the historical range, task dependencies, and reading `XCom`/return values between tasks. Confirm a triggered backfill reproduces the trained model.
- **Day 11** — FastAPI service loading the registered model; `/predict` + `/health`; Dockerfile.
- **Day 12** — Streamlit dashboard: score Applyhome launches, rank by estimated premium (predicted resale − base price), risk flags. `docker-compose` wiring FastAPI + Streamlit + MLflow.
- **Day 13** — README (architecture, quickstart, results table, known limitations), Makefile, `.env.example`, reproducibility test.
- **Day 14** — Buffer / polish / demo GIF / cut-line recovery.

---

## 6. MoSCoW (what to sacrifice when behind)

- **Must:** MOLIT ingestion w/ encoding+retry, point-in-time features, time-split LightGBM, MLflow registry, **Airflow DAG (ingest→FE→train, retries + backfill)**, FastAPI+Docker, README with limitations.
- **Should:** Streamlit dashboard, ECOS macro features.
- **Could:** Evidently drift, Optuna tuning, all three comp radii.
- **Won't (this round):** S3/MinIO, XGBoost/CatBoost ensemble, W&B, cloud deploy, fair-value-vs-premium modeling.

---

## 7. Known Limitations (put this section in the README — it's the senior signal)

- **Label is realized resale price**, so predicted "premium" is market-relative, not fundamental value.
- **Regulatory regime not modeled** — 분양가상한제, 전매제한, 규제지역 status dominate premium mechanics and shift across 2020+ regimes; training sample is selection-biased toward periods/areas where transfer was legal. A drift monitor won't catch a relationship that inverts when rules change.
- **Comps lagged ~30d** to reporting delay to avoid look-ahead.
- **Officetel/apartment pooling** introduces noise (different tax, demand, usable-space); 전용률 used to mitigate.
- **Single region** — not nationwide-generalizable as-is.

Naming these is worth more than a higher R². Naive projects hide weaknesses; strong ones name them.

---

## 8. Cost Control

Fully local: free government APIs, DuckDB, Docker. **~Zero cost.** No GCP required. Cloud deploy is an optional stretch, not part of the 2-week scope.

---

## 9. Definition of Done

- `docker-compose up` brings up FastAPI + Streamlit + MLflow with a registered model serving live predictions.
- One command runs backfill → feature build → retrain.
- README reports test RMSE / MAPE / R² on a **time-based** split, plus the leakage audit and limitations section.
- Repo clones and runs on a fresh machine from the README alone.
