# Cancellation / re-offer (무순위·잔여세대 재공급) feature — CANDIDATE, deferred

Status: **documented for later** (2026-07-29). 청약홈 exposes a distinct feed for
units that were cancelled/forfeited by original winners and then re-offered. This
is a demand-weakness signal, not yet built.

## What exists (probed live, data.go.kr account key works)

| Operation | Service | Rows | Content |
|---|---|---|---|
| `getRemndrLttotPblancDetail` | ApplyhomeInfoDetailSvc | 1,639 공고 | 무순위/잔여세대 재공급 announcements: 주택명, HSSPLY_ADRES, 공고일(RCRIT_PBLANC_DE), 입주예정, 세대수(TOT_SUPLY_HSHLDCO), **계약체결기간**(CNTRCT_CNCLS_BGNDE/ENDDE) |
| `getRemndrLttotPblancCmpet` | ApplyhomeInfoCmpetRtSvc | 4,157 | per-주택형 competition for the re-offer, with **`REMNDR_HSHLD_PBLANC_TYCD`** = 재공급 유형 (무순위 vs 계약취소 재공급) |

These are the "cancelled subscription → re-subscription" records: when original
winners are 부적격/미계약/계약취소, leftover units get re-offered (무순위 청약).

## Why it's a useful signal
A launch generating 무순위/재공급 = original demand was **weaker than headline
경쟁률 suggested** (winners walked away). Expected to correlate with **lower resale
premium** — same spirit as `ah_undersubscribed`, but captures *post-award* fallout
the initial 경쟁률 misses.

Candidate features (join to matched label complex by PBLANC/name+area):
- `ah_had_reoffer` (bool) — any 무순위/재공급 for this launch
- `ah_reoffer_units` / `ah_reoffer_ratio` — leftover units ÷ total 세대
- `ah_reoffer_type` — 무순위 vs 계약취소 재공급

## Leakage discipline (invariant #3)
Post-original-subscription outcome → **only join when the re-offer 공고일 ≤ resale
deal_date** (same guard as 경쟁률). A re-offer that happened *after* the resale must
never enter that row. Encode as a test, mirroring `ml_pipeline/tests/test_enrich.py`.

## Open question — matching key
Re-offer 공고 has its **own PBLANC_NO** (≠ the original 분양 PBLANC). So joining to a
label row goes via **base_name(house_name) + 시도 + 전용면적** (the fuzzy path), then
the date guard — not the PBLANC join used for the primary 분양가 enrichment. Verify
match rate before committing (same method as the 청약홈 coverage analysis).

## Resume checklist
1. `extract_reoffer()` in `extract/applyhome.py` (mirror `extract_competition`), land
   `data/raw/applyhome_reoffer/`.
2. Aggregate per (name, 시도, 전용) + earliest re-offer 공고일.
3. Join in `features/enrich.py` behind the `공고일 ≤ deal_date` guard; add ah_* cols.
4. Measure coverage + premium correlation (expect negative) before finalizing.

Related: [[applyhome-training-enrichment]] (the enrichment invariant + 경쟁률 build);
docs/applyhome_features.md (primary + competition features already built).
