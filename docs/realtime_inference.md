# Real-time inference & the slow ↔ fast data line

Status: **partially built** (updated 2026-07-30). Captures which datasets are static
vs time-varying, and what real-time signal feeds live inference. The **MOLIT 실거래가
daily refresh is now built** (see "What's fetchable today" below and
docs/daily_incremental_job.md); the remaining FAST/event-driven sources are still
roadmap and guide the serving layer (Day 11–12) and future feature work.

## The core distinction

Training is batch. **Inference scores a property "as of now"** — either an upcoming
청약홈 launch (pre-subscription) or an existing 분양권 that could be resold. A
feature only benefits from being *real-time* if its value **changes between now and
the last batch build AND that change moves the prediction.** Most features don't;
a few do.

**Hard rule (leakage parity):** every real-time feature MUST have a training-time
counterpart computed with the same point-in-time rule (as-of `deal_date`). A live
signal with no leakage-safe historical analog **cannot be trained on** — it would
be a feature the model never saw. Same discipline as the 청약홈/경쟁률 guards.

---

## What's fetchable *today* (built) vs. roadmap

A quick answer to "what can we actually fetch for real-time value inference right now":

| Signal | Fetchable now? | How | Point-in-time analog |
|---|---|---|---|
| **MOLIT 실거래가 comps** (freshest nearby apt sales) | ✅ **BUILT** | `make refresh` / `molit_realtime_refresh` DAG → daily trailing-window re-fetch + first-seen ledger | comps filtered by `first_seen_date ≤ prediction_date` — **exact**, no +30d guess |
| **MOLIT 분양권 label freshness** (updates the "resold rights" scoring universe) | ✅ **BUILT** | same daily job, `label` feed | ledger tracks first-seen / 해제 / 등기 per deal |
| **cancellation-rate signal** (해제 / reports, demand weakness) | ✅ derivable | ledger `cancelled_date` vs `first_seen_date` per 시군구 | same ledger, as-of any past date |
| ECOS macro (monthly print) | ✅ existing extractor | pull latest monthly value at inference | as-of `deal_date` |
| 청약홈 launch facts + 경쟁률 (enrich scoring list) | ⚠️ partial | odcloud — **분양정보 svc in outage; 경쟁률 svc healthy**; covers 6 of 9 시도 (missing 울산·세종·광주 until recovery) | 공고일 ≤ deal_date guard (invariant #3); null-safe when absent |
| R-ONE 주간 가격동향, ECOS daily 국고채, Naver DataLab | ❌ roadmap | official free APIs, not yet wired | see FAST table below |
| 네이버 부동산 호가·매물 | ❌ excluded | no official free API (ToS / zero-cost) | — |

**Real-time inference today** = static features from the batch lake **+** fresh MOLIT
comps as-of now (the daily refresh keeps the lake current; the ledger lets us filter
comps to exactly what was publicly visible by the prediction date). Everything else
in the FAST/event-driven tiers below is designed but not yet built.

---

## The slow ↔ fast line (every dataset classified)

### STATIC — infrastructure / fixed attributes (rebuild rarely, no real-time)
| Dataset | Why static |
|---|---|
| transit (metro/bus coords) | physical infrastructure; changes only when a line opens |
| schools (NEIS locations) | school locations barely move |
| schoolinfo (학군 type/진학률) | annual disclosure, 3-yr API window → near-static snapshot |
| commercial (상가 POIs) | store turnover slow; quarterly at most |
| applyhome launch facts (분양가/입주예정/세대수/brand) | **fixed at 공고 time** — never change after |
| property attributes (area/floor/right_type) | intrinsic |

*Refresh cadence: monthly-to-quarterly batch is plenty. No inference-time fetch.*

### SLOW — periodic, use latest value at inference (monthly)
| Dataset | Cadence | Real-time upgrade available? |
|---|---|---|
| ECOS macro (기준금리, M2, CSI, mortgage) | monthly | yes → daily bond-yield lead (see FAST) |

*At inference: pull the latest monthly print. Cheap, low-frequency.*

### FAST — genuinely time-varying, benefit from freshness at inference
| Dataset | Signal | Cadence | Access |
|---|---|---|---|
| **MOLIT 실거래가 (comps)** | freshest nearby sales — the core spatial feature | daily (30d report lag) | ✅ **BUILT** — daily refresh + first-seen ledger |
| **한국부동산원 R-ONE 주간 가격동향** | market momentum by 시군구 (rising/cooling now) | weekly (Thu) | ✅ official OpenAPI (new) |
| **ECOS daily 국고채 yield** | rate leading indicator (moves before monthly mortgage) | daily | ✅ have ECOS key |
| 네이버 DataLab 검색 트렌드 | demand nowcast (search interest in region/complex) | daily | ✅ free Naver API (new key) |

### EVENT-DRIVEN — irregular, fire on occurrence
| Dataset | Signal | Trigger |
|---|---|---|
| 청약 경쟁률 | realized demand for a launch | posts days after subscription |
| 규제지역 지정/해제 | 투기과열/조정 regime flip (big premium driver) | MOLIT 고시 (irregular) |
| cancellation / 무순위 재공급 | post-award demand weakness | re-offer 공고 |

### EXCLUDED — best leading signal, wrong fit
| Dataset | Why excluded |
|---|---|
| 네이버 부동산 / 호갱노노 호가·매물 | asking prices + listing volume are the *most* real-time leading indicator, but **no official free API** — scraping breaks the project's zero-cost / clean-source / ToS constraints. Documented as "known best signal we won't use." |

---

## Recommended real-time layer (fits existing constraints/keys)

Three upgrades, all reusing access we already have or free official APIs:

1. **Fresh comps** — ✅ **BUILT** (2026-07-30). The `molit_realtime_refresh` daily job
   re-fetches the MOLIT 실거래가 trailing window and updates a first-seen ledger, so
   spatial comp features reflect sales up to today (not the training snapshot) and
   can be filtered to exactly what was publicly visible as-of the prediction date.
   Highest value, zero new source. See docs/daily_incremental_job.md.
2. **Weekly momentum** — add R-ONE 주간 아파트가격지수 for the property's 시군구.
   Training analog: join the index as-of each row's `deal_date` week.
3. **Daily rate lead** — use ECOS daily 국고채 yield instead of the monthly mortgage
   print. Training analog: as-of `deal_date` daily yield.

`네이버 DataLab` search-trend nowcast is a possible 4th (free key) but weaker/noisier.

## Serving-layer implication
The FastAPI service should, per request: (a) resolve the property's static features
from the batch lake, (b) fetch/refresh the FAST features as-of *now*, (c) assemble
the same vector the model trained on. Cache FAST pulls (e.g. comps per 시군구,
weekly index) so concurrent requests don't re-hit the APIs.

The **scoring universe itself** (which upcoming 분양 launches to score, with location /
slots / types / 분양가 / odds) is specified in docs/upcoming_launches.md — the
inference end of this slow↔fast line.

Related: [[transport-reference-data]] (static infra), docs/applyhome_features.md
(event-driven 경쟁률), docs/upcoming_launches.md (scoring universe),
docs/work_area_accessibility.md, docs/cancellation_reoffer_feature.md.
