# Korea Real Estate MLOps — Pre-Sale Rights Valuation

Predict the **realized resale price (KRW per ㎡)** of Korean pre-sale rights
(분양권) for **Seoul + Gyeonggi** through a **GCP-native MLOps pipeline**:
ingest → GCS Parquet → BigQuery → Vertex AI. The deliverable is a clean,
reproducible, **leakage-free** pipeline — legibility over model surface area.

> How-to-build rules for contributors: `CLAUDE.md`.
> Target repo architecture & platform boundaries: `repo_instruction.md`.
> Full plan & sequencing: `docs/presale_pipeline_2week_scope.md`.

## Architecture

Two pillars with a **BigQuery contract** (`korea_real_estate.*`) as the only boundary:

```
DATA PILLAR  (data_pipeline/)                 Orchestrated by Airflow (Astro CLI)
  [MOLIT / ECOS / VWorld / Applyhome / NEIS / 상권 extractors]
        │  encoding auto-detect + tenacity retry + pydantic validation
        ▼
  [Hive-partitioned Parquet]  ──sync──►  [GCS raw lake]  ──load──►  [BigQuery korea_real_estate.*]
                                                                          │
── contract boundary ─────────────────────────────────────────────────── │ ──
                                                                          ▼
ML PILLAR  (ml_pipeline/)                     Orchestrated by Vertex AI Pipelines (KFP v2)
  [preprocess: BigQuery → point-in-time feature matrix → features table]
        ▼
  [train: time-split · LightGBM / XGBoost / scikit-learn]  ──►  [Vertex AI Experiments + Model Registry → serving]
```

- **Airflow (Astro)** owns ingestion — per-source DAGs (daily label+comps, weekly
  launches, monthly macro, quarterly commercial) refresh the lake and push each
  source to **GCS + BigQuery**.
- **Vertex AI Pipelines (Kubeflow SDK v2)** owns ML — `pipeline.py` wires the same
  importable `ml_pipeline` functions; training/eval/serving all run Vertex-side.
- GCP auth is **Application Default Credentials** (no keys in code).

## Data sources

| Source | Role |
|---|---|
| MOLIT 분양권전매 실거래가 | **Training label** (resale price/㎡) + features |
| MOLIT 아파트 매매 | Comparable-sale (comps) features |
| ECOS (Bank of Korea) | Macro features (base rate, mortgage yield, M2, CSI) |
| VWorld / Kakao Local | Geocode complexes; nearest-station distance |
| Applyhome (청약홈) | Launch-time enrichment (분양가/입주예정/세대수/brand, `공고일 ≤ deal_date`) + upcoming-launch inference list |

## Quickstart

```bash
make setup            # uv sync, cache GCS reference lookups, copy .env.example -> .env
# fill gov-API keys in .env; set GCP_PROJECT_ID / GCS_BUCKET / BQ_DATASET (or config.yaml)
# GCP creds via ADC: gcloud auth application-default login  (or GOOGLE_APPLICATION_CREDENTIALS)
make backfill         # historical ingest 2016 -> present (local Parquet)
make lake-to-bq       # mirror raw lake to GCS, load into BigQuery contract tables
make features         # preprocess: BigQuery -> features table
make train            # time-split train (LightGBM/XGBoost/sklearn) + Vertex experiment log
make test             # pytest — includes leakage + time-split invariant tests
make astro-start      # local Airflow (ingest DAGs) via the Astro CLI
make compile-pipeline # compile the Vertex AI (KFP v2) pipeline; submit-pipeline to run on Vertex
```

Requires Python 3.11+, [`uv`](https://docs.astral.sh/uv/), a GCP project
(BigQuery + GCS + Vertex AI enabled), and the [Astro CLI](https://docs.astronomer.io/astro/cli/overview)
for local Airflow.

## Results

_Reported on the held-out **time-based** test set (most recent slice)._

| Metric | Value |
|---|---|
| RMSE | _TBD_ |
| MAPE | _TBD_ |
| R² | _TBD_ |

Leakage audit: _TBD_ (see `ml_pipeline/tests/test_leakage.py`).

## Known Limitations

- **Label is realized resale price**, so predicted "premium" is market-relative,
  not fundamental value.
- **분양가 anchors the label (≈ 1-to-1), which inflates headline accuracy.**
  Empirically, the MOLIT 분양권 전매 price is the *full* value of the right (분양가 +
  premium): across matched rows the resale/분양가 ratio is tightly centred (median
  **1.04**, IQR 0.99–1.10, 95th pct 1.52, with a real 마이너스-프리미엄 tail below
  1.0). Because 청약홈 **분양가 is a leakage-free feature with perfect inference
  parity**, a model that essentially predicts `resale ≈ 분양가` already lands within
  ~4% at the median — so **RMSE / MAPE / R² look strong largely because 분양가 sets
  the level.** The genuine signal is the *premium deviation* (±4%→±50%, driven by
  location, timing, macro, 세대수). We therefore also report error **on the
  premium/ratio**, not just price.
- **Regulatory regime not modeled** — 분양가상한제 / 전매제한 / 규제지역 status
  dominate premium mechanics and shift across 2020+ regimes; the training sample
  is selection-biased toward periods/areas where transfer was legal.
- **Comps lagged ~30d** to reporting delay to avoid look-ahead.
- **Officetel/apartment pooling** adds noise (different tax/demand/usable-space);
  전용률 used to mitigate.
- **청약홈 enrichment starts at 2020.** Launch-time features are null for
  pre-2020-launch resales and populated for ~90–96% of the recent test period.
  Tree models handle the nulls natively; the join is guarded by `공고일 ≤ deal_date`
  (no look-ahead, enforced in `ml_pipeline/tests/test_enrich.py`).
- **경쟁률 (subscription competition) is EDA/dashboard-only** — a post-subscription
  outcome, unknown at launch, so it never enters training.
- **Single region** — not nationwide-generalizable as-is (region is a config value).
