# Daily incremental job — MOLIT 실거래가 (real-time freshness)

Design for the daily job that keeps the MOLIT 실거래가 lake fresh for real-time
inference. Covers **both feeds** — 분양권 (SilvTrade, label) and apt-trade
(AptTrade, comps). Reuses the existing extractors; adds scheduling, reconciliation,
and an as-of ledger. Status: **design (approved 2026-07-30), ready to implement.**

## Why a daily job (the three things that change)
The current month is daily-fresh but **incomplete and mutable** (verified live):
1. **Late reports** — 계약 후 30일 내 신고 의무 → the last ~30 days keep growing for a
   month. (e.g. a 07-15 contract may first appear on 08-10.)
2. **Cancellations** — a reported deal can later be 해제 (`cdealType` set).
3. **등기 backfill** — `rgstDate` (등기일자) fills in weeks after the deal.

A one-shot append would miss (2) and (3) and lag on (1). So the job **re-fetches a
trailing window and replaces it wholesale** each day.

---

## Core design

### 1. Trailing-window re-fetch + full-month replace (= reconciliation)
Reuse the existing `extract(mode="incremental")` in `extract/molit.py` and
`extract/molit_apt.py`. Incremental mode already:
- fetches only the trailing `ingest.trailing_refresh_months` window, and
- **replaces those months wholesale** (`existing[~deal_ym.isin(refetched)]` then
  re-concat) — so cancellations, late reports, and 등기 updates all reconcile
  automatically. Idempotent: re-running the same day is a no-op change.

**Change:** bump `trailing_refresh_months` 2 → **3** for the daily job (safety margin
beyond the 30-day window; cancellations occasionally land later).

### 2. As-of ledger (`first_seen_date`) — the leakage-exact upgrade
Full-month replace keeps the lake *current* but **loses the history of when each
deal became visible.** For rigorous point-in-time training we currently approximate
reporting lag as a flat 30 days (invariant #1). A tiny append-only ledger removes
the approximation:

```
data/realtime/seen_ledger/{feed}.parquet   (append-only, dedup on deal_key)
  deal_key            = hash(region, aptNm, jibun, excluUseAr, floor, deal_date, dealAmount)
  first_seen_date     = date this job first observed the row
  last_seen_date      = last date still present (for cancellation detection)
  cancelled_date      = date cdealType first appeared (else null)
  rgst_filled_date    = date rgstDate first appeared (else null)
```

Enables: (a) train on the **true** reporting lag (`first_seen_date`, not +30d
guess); (b) reconstruct "what was known as of any past date" exactly; (c) a
**cancellation-rate** feature (cancels / reports) as a demand-weakness signal.

### 3. Daily delta / audit output
Each run logs a small summary (for monitoring + a market-activity signal):
```
run_date, feed, region, n_new, n_cancelled, n_rgst_filled, n_total_window
```
Written to `data/realtime/deltas/{run_date}.parquet`. Cheap; powers "is the market
active this week" and pipeline health checks.

---

## Scope & scheduling
- **Feeds:** both — 분양권 (label) + apt-trade (comps). Comps are the real-time
  feature; label freshness matters for the inference scoring list.
- **Regions:** full configured scope by default; optionally a "hot subset" (only
  regions with an upcoming launch to score) to cut API load.
- **Schedule:** Airflow `@daily` (early morning KST, after MOLIT's overnight
  publish). TaskFlow DAG calls the importable `extract(mode="incremental")` — no
  business logic in the DAG (per CLAUDE.md). A `Makefile` target `make refresh`
  runs it manually.
- **Rate/quota:** trailing 3 months × regions is a fraction of a full backfill;
  well within daily quota. Rollover-safe (manifest) as today.

## Point-in-time / leakage discipline
- Training features still obey invariant #1. With the ledger, switch the comp
  filter from `deal_date + 30d ≤ prediction_date` to
  `first_seen_date ≤ prediction_date` — **exact**, no approximation.
- Real-time inference: comps = rows with `first_seen_date ≤ today` and not
  cancelled-as-of-today. Same code path, `prediction_date = today`.

## Failure modes handled
| Risk | Handling |
|---|---|
| Job runs twice/day | full-month replace is idempotent |
| API partial outage (e.g. 호남 gap) | region returns 0 → month replaced with empty; ledger keeps prior `last_seen` so a real cancellation isn't confused with an outage → **guard: only mark cancelled if the region returned data that day** |
| Late report after window | 3-month window covers ~99%; ledger's `first_seen` still correct when it lands |
| Mid-run stop | existing manifest rollover-safety |

## Components — BUILT (2026-07-30)
1. `src/presale/extract/realtime.py` — `refresh_feed(feed)` / `refresh(feeds)`;
   feed adapters (`_normalize_label`/`_normalize_comps`) → common ledger schema;
   `update_ledger` (first-seen + cancel/등기 transitions); `write_audit`.
2. `dags/realtime_refresh_dag.py` — TaskFlow `@dag` `molit_realtime_refresh`,
   `schedule="@daily"`, `catchup=False`, `max_active_runs=1`; two feed tasks
   (label serialised before comps for the shared MOLIT rate limit) → `write_daily_audit`.
3. `data_pipeline/scripts/refresh.py` + `make refresh`.
4. `data_pipeline/tests/test_realtime.py` — first-seen + idempotency, cancel/등기 transition,
   outage safety, label normaliser. (54 tests pass overall.)
5. Config `ingest.trailing_refresh_months: 3`; `realtime.{feeds,ledger_dir,delta_dir}`.

### Outage safety — simpler than first designed
The ledger only ever *adds* facts from rows **present** in a fetch; MOLIT surfaces a
해제 as a row with `cdealType` set (not a deletion). So a 0-row day (e.g. the 호남
gap) yields no updates — cancellation can never be inferred from absence. No separate
guard needed; it's safe by construction (tested in `test_outage_day_is_safe`).

## Follow-up (not blocking)
Atomic partition writes: switch `write_region_parquet` from rmtree+write to
temp-file + `os.rename` so a live FastAPI reader never sees a half-written file
during the daily refresh. Small shared-function change; deferred.

Related: [[molit-label-decision]], docs/realtime_inference.md (slow↔fast line),
CLAUDE.md invariant #1 (point-in-time comps).
