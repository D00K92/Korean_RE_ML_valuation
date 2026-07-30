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
- **분양가 anchors the label (≈ 1-to-1), which inflates headline accuracy.**
  Empirically, the MOLIT 분양권 전매 price is the *full* value of the right (분양가 +
  premium), not a premium-only figure: across matched rows the resale/분양가 ratio
  is tightly centred (median **1.04**, IQR 0.99–1.10, 95th pct 1.52, and a real
  마이너스-프리미엄 tail below 1.0). Because 청약홈 **분양가 is a leakage-free feature
  with perfect inference parity**, a model that essentially predicts
  `resale ≈ 분양가` already lands within ~4% at the median — so **RMSE / MAPE / R²
  look strong largely because 분양가 sets the level.** The genuine signal is the
  *premium deviation* (the ±4%→±50% spread driven by location, timing, macro,
  세대수). We therefore also report error **on the premium/ratio**, not just on
  price, so the metrics reflect whether the model learns the hard part rather than
  echoing 분양가. (Enrichment coverage is ~90–96% on the recent test period and ~0%
  pre-2020, since 청약홈 data starts in 2020 — see below.)
- **Regulatory regime not modeled** — 분양가상한제 / 전매제한 / 규제지역 status
  dominate premium mechanics and shift across 2020+ regimes; the training sample
  is selection-biased toward periods/areas where transfer was legal. A drift
  monitor won't catch a relationship that inverts when rules change.
- **Comps lagged ~30d** to reporting delay to avoid look-ahead.
- **Officetel/apartment pooling** adds noise (different tax/demand/usable-space);
  전용률 used to mitigate.
- **청약홈 enrichment starts at 2020.** Launch-time features (분양가,
  months-to-completion, 세대수, brand) come from the 청약홈 platform, which only
  covers 2020+ (pre-2020 subscriptions ran through 아파트투유, not exposed by this
  API). So these features are null for pre-2020-launch resales and populated for
  ~90–96% of the recent test period. LightGBM handles the nulls natively; the
  join is guarded by `공고일 ≤ deal_date` (no look-ahead, enforced in
  `tests/test_enrich.py`).
- **경쟁률 (subscription competition) is EDA/dashboard-only** — it is a
  post-subscription outcome, unknown at launch, so it never enters training
  (would be leakage and has no inference parity for pre-subscription launches).
- **Single region** — not nationwide-generalizable as-is (region is a config
  value, not a rewrite).
