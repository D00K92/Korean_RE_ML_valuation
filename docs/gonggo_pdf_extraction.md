# 입주자모집공고문 PDF extraction — regulatory regime

Status: **BUILT (2026-07-31).** Extracts the regulatory regime (전매제한 / 분양가상한제 /
실거주의무 / 규제지역 / 택지유형) from 청약홈 입주자모집공고문 PDFs — fields the odcloud
API does **not** expose. Enriches the MOLIT 분양권 label under invariant #3.

## Why the PDF (what the API can't give)

The odcloud 분양정보/경쟁률 APIs give prices, units, dates, and demand — but **nothing
about the regulatory regime**, which is a first-order driver of 분양권 resale:

- **전매제한 기간** gates *whether/when* a right can be resold at all (the resale universe).
- **분양가상한제 적용여부** → 상한제 units carry longer restrictions + 실거주의무.
- **규제지역 (투기과열/조정) at launch** drives LTV, 전매제한, premium.

These directly upgrade two README **Known Limitations** ("regulatory regime not
modeled", "selection bias from 전매제한") into modeled features.

## Where it lives in the PDF — and the hard scope decision

The fields sit in a **compact summary box** near the top of the 공고문:

```
투기과열지구/청약과열지역 | 재당첨제한 | 전매제한 | 거주의무기간 | 분양가상한제 | 택지유형
      (status)         |   10년    |   3년   |    없음    |   미적용   | 민간택지
```

**This box is format-consistent only for 2024+ launches** — verified, not assumed:

| Era | Format | Decision |
|---|---|---|
| **2024–2026** | compact box, one layout | ✅ **in scope** — parse deterministically |
| 2020–2023 | fields scattered in prose / different mini-tables; 실거주의무 often genuinely absent (post-2021 law) | ❌ out of scope (also where 청약홈 enrichment is already sparse) |
| any era, **LH 신혼희망타운/공공분양** | frequently **image-only PDFs** (no text layer) | ⏭️ skipped → null (owner decision 2026-07-31) |

Scoping at 2024 aligns with the **time-based split**: the box is consistent exactly
in the recent test window and inference-scoring period that drive the metrics.

## Measured extraction quality (40-doc in-scope 2024+ sample)

- **86%** of non-image launches parsed (30/35) with the hardened label-anchored parser.
- Values are **regime-correct and internally coherent**: 분양가상한제 적용 ⇒ a 실거주의무
  and longer 전매제한 (e.g. 디에이치 대치 3년/2년/적용/투기과열; most 민간 비규제 6개월/없음/미적용).
- Remaining misses = borderless boxes (text-regex fallback recovers most) + a few 공공.

## How the parser works (deterministic, no LLM)

1. **Fetch** — the PDF URL is *not* in the API; scrape the `getAtchmnfl.do` link off the
   청약홈 detail-page HTML, download from the static host (**no API key**), disk-cache.
2. **Parse** — `pdfplumber` ruled-table extraction, **label-anchored**: for each header
   cell (전매제한/거주의무/분양가상한제/…) take the cell directly beneath it (robust to
   column drift). **Text-regex fallback** for borderless boxes.
3. **Validate** — the `GonggoRegulatory` pydantic model normalises 년/개월/없음 → months
   and 적용/미적용 → bool.

**Why no local LLM** (evaluated and rejected): these are government-ruled tables with a
text layer, so `pdfplumber` extracts prices **to the won** and regulatory values exactly.
An LLM was only ever insurance for layout drift; with the 2024+ scope the layout is
consistent, so it's unnecessary. If a future need arises, an LLM (or a metered cloud
call) is reserved *only* for the residual that fails validation — deterministic first.

## Validation without an API ground truth

Unlike price (which cross-checks against `LTTOT_TOP_AMOUNT`), these fields have **no API
anchor**. Trust rests on two external checks:
- **Internal coherence** — 분양가상한제 적용 ⇒ 실거주의무 present ⇒ longer 전매제한.
- **규제지역 고시 history** — public MOLIT 고시 gives ground truth by region + date
  (e.g. 강남 3구 remained 투기과열 after the 2023 완화; everywhere else de-regulated).

## Leakage discipline (invariant #3)

Every field is **fixed at 공고 time**, so it joins to a resale row only when
`공고일 <= deal_date` — the same guard `features/enrich.py` already applies to the other
청약홈 launch-time fields. `notice_date` is carried on each row for that guard.

## Components — BUILT

1. `src/presale/schemas/gonggo.py` — `GonggoRegulatory` (년/개월/없음→months, 적용→bool).
2. `src/presale/extract/gonggo.py` — `download_gonggo` (scrape+cache), `parse_regulatory`
   (table + text fallback), `extract(launches)` → land `data/raw/gonggo/`.
3. `data_pipeline/scripts/fetch.py --source gonggo [--limit N]` — launch universe from
   `extract.gonggo.list_launches` (2024+ from the applyhome lake).
4. `data_pipeline/tests/test_gonggo.py` — months/bool normalisation, coherence, fallback, URL scrape.
5. Config `sources.applyhome.gonggo` (min_year 2024, cache_dir, hosts).

## Follow-up (not blocking)

- **Floor-band 분양가** from the 공급금액 table (the one price the API flattens — proven
  exact vs API to the won). Same PDF, second parser; deferred.
- OCR fallback for LH image-only PDFs (currently null) — only if coverage demands it.
- Feature wiring in `features/enrich.py` + a leakage test on the 공고일 guard.

Related: docs/applyhome_features.md (API enrichment + join/leakage guard),
docs/upcoming_launches.md (scoring universe), [[applyhome-training-enrichment]].
