# Upcoming 분양 — the inference scoring universe

Status: **design (approved 2026-07-30), build in the Day 11–12 serving pass.**

What is the set of properties the model *scores* at inference time? For 분양권 resale
prediction it is the list of **recent + upcoming 청약홈 launches** — each one a right
that will (or already can) be resold. CLAUDE.md invariant #3 explicitly reserves this
role for 청약홈: *"Applyhome still produces the 'upcoming launches to score' inference
list."* This doc specifies that producer.

It is **not** a new data source — it reuses the three odcloud pulls we already have
(`extract/applyhome.py`). It adds an *orientation* (upcoming, not the full 2020+
catalog), keeps two timing fields the enrichment extractor discards, and geocodes the
launch address so the row can carry the same spatial features the model trained on.

---

## What one scoring row is

One row per **launch × 주택형** (same grain as the enrichment catalog), carrying:

| Field | odcloud source | Notes |
|---|---|---|
| location | `HSSPLY_ADRES` → geocoded lat/lon | 지번; run through the existing VWorld cascade |
| total slots | `TOT_SUPLY_HSHLDCO` | complex scale |
| **per-type slots** | `SUPLY_HSHLDCO` | **currently dropped by `extract()` — must keep** |
| type / 전용면적 | `HOUSE_TY` (parse leading number) | not `SUPLY_AR` (공급면적) |
| price (분양가) | `LTTOT_TOP_AMOUNT` (만원) | feature **and** dashboard premium baseline |
| 입주예정 | `MVN_PREARNGE_YM` | → months_to_completion at score date |
| builder | `CNSTRCT_ENTRPS_NM` | brand |
| **접수 dates** | `RCEPT_BGNDE`, `PRZWNER_PRESNATN_DE` | **currently dropped — define "upcoming"** |
| odds | `경쟁률` (`REQ_CNT ÷ SUPLY_HSHLDCO`) | **only if past 당첨자발표** — see below |
| `odds_available` | derived | True once 경쟁률 is published, else False |
| `launch_stage` | derived | `pre_receipt` \| `subscribed` \| `resaleable` |

The static/spatial features (transit, schools, 학군, commercial proximity, macro) are
assembled for the row exactly as at training — same functions, `prediction_date =
today`. This is what keeps the scoring vector identical in shape to the trained one.

---

## The "upcoming" window (scope: recent + upcoming, flagged)

Include a launch if **either**:

- `RCEPT_BGNDE >= today − buffer` (future or currently-open subscription — *upcoming*), **or**
- `RCRIT_PBLANC_DE >= today − 6 months` (recently launched, may not yet be resold).

Rationale: the widest useful set spans "about to launch" through "just launched, not
yet resold." A single window would either miss the earliest signal or drag in stale
launches. `launch_stage` + `odds_available` let the serving layer and dashboard filter
without re-querying.

Window bounds (`upcoming_lookback_months: 6`, `receipt_buffer_days`) go in
`config/settings.yaml` under `sources.applyhome`, not hardcoded.

---

## The odds-timing rule (hard constraint, not a choice)

경쟁률 is published **only after 청약접수 closes** (≈ 당첨자발표일). So:

| `launch_stage` | Trigger | odds |
|---|---|---|
| `pre_receipt` | `today < RCEPT_BGNDE` | **null** (`odds_available = False`) |
| `subscribed` | 접수 done, `today < PRZWNER_PRESNATN_DE` | usually still null |
| `resaleable` | past 당첨자발표 (+ 전매제한 window) | populated |

A genuinely upcoming launch therefore scores from location/slots/type/분양가 **without
demand info** — the model must not *require* 경쟁률 (LightGBM handles the null; the
training-time feature was already null for pre-2020 and unmatched rows).

**Leakage parity holds.** When odds *are* present they are safe to use: 청약일 always
precedes any 분양권 resale, so 경쟁률 is a pre-existing covariate as-of the resale
`deal_date` (the same guard `enrich.py` applies for training — see
docs/applyhome_features.md). No new leakage surface.

---

## Dashboard use of 분양가

분양가 is a model feature **and** the display baseline: the dashboard shows
`predicted resale − 분양가` as the estimated premium (마피 when negative). Computed
post-prediction, display-only — **never** as a `resale ÷ 분양가` feature (target
leakage; see applyhome_features.md).

---

## What to build (Day 11–12)

Small additions, all reusing existing code:

1. `extract/applyhome.py` — keep `RCEPT_BGNDE`, `PRZWNER_PRESNATN_DE`, and per-type
   `SUPLY_HSHLDCO` (schema + `extract()` currently discard them). Backward-compatible
   (new nullable columns; enrichment ignores them).
2. `features/`(serve) — `upcoming_launches(as_of=today)`: filter the catalog to the
   window above, derive `launch_stage` / `odds_available`, geocode `HSSPLY_ADRES`,
   attach static/spatial + macro features as-of `as_of`, attach odds where available.
   Output = the scoring frame the model consumes.
3. Serving (`serve/api.py`, `serve/app.py`) — endpoint returns scored upcoming
   launches; dashboard lists them with predicted resale + 분양가 premium.
4. Tests — `pre_receipt` row has null odds; `resaleable` row's odds obey the 청약일 ≤
   deal_date guard; window boundaries; geocode-miss is null-safe.

## Known limits (carry to README)

- **호남 gap**: 광주(29) 분양정보 currently un-ingestible (provider-side); those launches
  won't appear until the odcloud service recovers.
- **odcloud 분양정보 outage** (2026-07-30): when the detail service is down, the
  scoring list is stale — degrade gracefully (serve last-good catalog + a freshness
  timestamp), don't fail.
- Pre-subscription launches are scored with no demand signal (by construction above).

Related: docs/applyhome_features.md (enrichment side, join + leakage guard),
docs/realtime_inference.md (slow↔fast line; this is the scoring end of it),
[[applyhome-training-enrichment]], CLAUDE.md invariant #3.
