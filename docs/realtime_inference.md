# Real-time inference & the slow ↔ fast data line

Status: **advisory / roadmap** (2026-07-29). Captures which datasets are static vs
time-varying, and what real-time signal could feed live inference. Nothing here is
built yet; it guides the serving layer (Day 11–12) and future feature work.

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
| **MOLIT 실거래가 (comps)** | freshest nearby sales — the core spatial feature | daily (30d report lag) | ✅ same extractor, run live |
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

1. **Fresh comps** — at inference, run the MOLIT 실거래가 extractor live so spatial
   comp features reflect sales up to today (not the training snapshot). Highest
   value, zero new source. Training analog: comps already point-in-time filtered.
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

Related: [[transport-reference-data]] (static infra), docs/applyhome_features.md
(event-driven 경쟁률), docs/work_area_accessibility.md, docs/cancellation_reoffer_feature.md.
