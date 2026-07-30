# 청약홈 Enrichment Features

Feature specification for the 한국부동산원 **청약홈** data used to enrich the MOLIT
분양권 resale label (and inference rows). Two odcloud services feed this:

| Service | odcloud id | Grain | Role |
|---|---|---|---|
| 분양정보 | `ApplyhomeInfoDetailSvc` | announcement ⨝ 주택형 | launch-time facts (분양가, 입주예정, 세대수, brand) |
| 청약접수 경쟁률 | `ApplyhomeInfoCmpetRtSvc` | PBLANC × 주택형 × 순위 × 거주지역 | demand signal (경쟁률) |

Scope: 수도권 (서울/경기/인천), **2020+** (청약홈 platform floor). Data is a *catalog*
(one row per launch × 주택형), joined onto the transaction-level label.

---

## Invariant #3 (rev 2026-07-29) — how 청약홈 may be used

청약홈 enriches **both training and inference**, but only with attributes that are
**public as of the row's `deal_date`**. Two guards:

- **Launch-time fields** (분양가, 입주예정, 세대수, brand) join when `공고일 <= deal_date`.
- **경쟁률** joins when `청약일 <= deal_date`. This always holds because subscription
  precedes any 분양권 resale, so competition is a *pre-existing* covariate, not
  leakage. (Corrects the earlier "경쟁률 never in training" stance.)

The label is **never** sourced from 청약홈. 분양가 is a feature *and* the dashboard's
premium baseline (`predicted resale − 분양가`), computed post-prediction.

⚠️ **Never** create a `resale ÷ 분양가` ratio feature — it divides by the label
(target leakage). 분양가 enters standalone; the model learns premium implicitly.

---

## Join mechanism

```
label row ──[ base_name(complex) + 시도 + 전용면적 ]──► 청약홈 announcement (PBLANC_NO)
   guard: 공고일 ≤ deal_date        pick closest 전용, latest 공고
   ⨝ 경쟁률 on (PBLANC_NO, 전용면적)
```

- `base_name()` = NFKC + strip parentheticals/블록/단지/차 (shared with the geocoder).
- 전용면적 parsed from `HOUSE_TY` leading number (e.g. `055.9200A` → 55.92), **not**
  `SUPLY_AR` (that is 공급면적).
- Unmatched → null (LightGBM handles natively).

---

## Feature catalog

### A. Launch-time (분양정보) — BUILT

| Feature | Source | Notes |
|---|---|---|
| `ah_supply_price_per_m2` | `LTTOT_TOP_AMOUNT` (만원) ÷ 전용 | 분양가 base price; dominant level driver |
| `ah_months_to_completion` | `MVN_PREARNGE_YM` − deal_date | marquee 분양권 driver; goes negative for 입주권-era trades |
| `ah_total_units` | `TOT_SUPLY_HSHLDCO` | complex scale |
| `ah_builder` | `CNSTRCT_ENTRPS_NM` | brand proxy |

### B. Demand / competition (경쟁률) — BUILT

Aggregate the (순위 × 거주지역) rows to per-(PBLANC × 주택형):

| Feature | Definition | Rationale |
|---|---|---|
| `ah_competition_rate` | Σ`REQ_CNT` ÷ `SUPLY_HSHLDCO` | headline demand; **ρ=0.277 with premium** |
| `ah_undersubscribed` | any 미달 `(△N)` / rate < 1 | 마이너스-프리미엄 risk marker |
| `ah_rank1_local_rate` | 1순위 해당지역 rate | most-watched competition number |
| `ah_local_demand_share` | 해당지역 접수 ÷ 총 접수 | locality-of-demand signal |

Do **not** parse `CMPET_RATE` string directly (30% 미달 `(△N)`, 48% `-` N/A);
compute the rate from `REQ_CNT` / `SUPLY_HSHLDCO`.

---

## Evidence

**분양가 ≈ resale (≈1-to-1).** The label is the *full* value of the right (분양가 +
premium), not premium-only: resale/분양가 median **1.04** (IQR 0.99–1.10, 95th 1.52,
마피 tail < 1.0). ⇒ 분양가 anchors the level and inflates headline R²/MAPE; report
error on the **premium** too, since that is the hard part.

**Competition predicts premium** (median resale ÷ 분양가 by 경쟁률 bucket):

| 경쟁률 | median premium |
|---|---|
| 미달 (<1) | 1.015 |
| 5–10 | 1.033 |
| 10–20 | 1.055 |
| 50+ | 1.078 |

Monotone, Spearman **ρ = 0.277**. Competition explains part of the premium
deviation 분양가 cannot.

---

## Coverage

- Enrichment matches **~22.9k label rows (10.7% overall)** but **~90–96% of the
  recent time-based test period** (2023–2026); ~0% pre-2020 (platform floor).
- Competition attaches to **22.0k rows (96% of enriched)** — same footprint.
- Nulls concentrate in the pre-2020 high-volume era (전매제한 collapsed post-2020
  resale volume), so they fall mostly outside the reported test slice.

**Known limitation:** pre-2020-launch resales have null 청약홈 features
(아파트투유 era, not in this API). See README Known Limitations.

---

## Status — BUILT

- `extract/applyhome.py` — `extract()` (분양정보) + `extract_competition()` (경쟁률 raw).
- `schemas/applyhome.py`, `features/enrich.py` — `enrich_labels(labels, applyhome,
  competition=None)` attaches sections A + B; `aggregate_competition()` collapses to
  per-(PBLANC, 전용) metrics. `tests/test_enrich.py` (5 tests incl. leakage guard).
- Config `ApplyhomeInfoCmpetRtSvc` block is `role: feature`.
- Verified end-to-end: 22.9k label rows enriched, competition Spearman ρ=0.28
  reproduced on the built pipeline, null-safe, 0 leakage violations.
- Lakes: `data/raw/applyhome/`, `data/raw/applyhome_competition/`.
