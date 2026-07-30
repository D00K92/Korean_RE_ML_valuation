# ECOS 가중평균금리 (weighted-average interest rates) — data dictionary

Reference dictionary for the **한국은행(BOK) 예금은행 가중평균금리** statistics used
(or available) as macro features. Every item code, its meaning, coverage, and
relevance to the 분양권 valuation model. Source: BOK ECOS OpenAPI.

## What "가중평균금리" means
A **weighted-average interest rate**: the average rate across many contracts,
weighted by each contract's amount. BOK publishes it monthly for 예금은행 (deposit
banks), split two ways:

- **수신금리 (deposit / funding rates)** vs **대출금리 (lending rates)**
- **신규취급액 기준 (new business)** vs **잔액 기준 (balance / outstanding)**

The **신규취급액 vs 잔액** distinction is the key one for modeling:
- **신규취급액 기준** = rate on contracts *newly made this month* → **leading,
  volatile, reflects today's marginal financing cost.** Best for "cost of buying
  now." **Use this for the model.**
- **잔액 기준** = weighted average over *all outstanding* contracts → lagging,
  smooth, reflects the stock. Useful as a slow-moving control, not the margin.

→ 4 tables: 수신·신규 (`121Y002`), 수신·잔액 (`121Y013`), 대출·신규 (`121Y006`),
대출·잔액 (`121Y015`). Unit = 연% (annual percent). Monthly (`CYCLE=M`).

⭐ = directly relevant to 분양권 valuation. Our current extractor uses
`121Y006/BECBLA0302` (주택담보대출) as `mortgage_rate`; `722Y001/0101000` = 기준금리.

---

## 121Y006 — 예금은행 대출금리 (신규취급액 기준) · **loan rates, new business**
The most model-relevant table (marginal cost of borrowing to buy).

| Item code | 명칭 | Meaning | From | ⭐ |
|---|---|---|---|---|
| `BECBLA01` | 대출평균 | **Weighted-avg lending rate, all loans** (the headline "가중평균금리") | 1996 | ⭐ |
| `BECBLA02` | 기업대출 | Corporate loans (avg) | 1996 | |
| `BECBLA0201` | 대기업대출 | Large-enterprise loans | 1996 | |
| `BECBLA0202` | 중소기업대출 | SME loans | 1996 | |
| `BECBLA0203` | 운전자금대출 | Working-capital loans | 1996 | |
| `BECBLA0204` | 시설자금대출 | Facility/capex loans | 1996 | |
| `BECBLA03` | 가계대출 | **Household loans (avg)** | 1996 | ⭐ |
| `BECBLA0301` | 소액대출 (500만원 이하) | Small loans (≤5M KRW) | 2001 | |
| `BECBLA0302` | 주택담보대출 | **Mortgage (home-secured loan)** — *current `mortgage_rate`* | 2001 | ⭐ |
| `BECBLA0303` | 예·적금담보대출 | Deposit-secured loans | 2001 | |
| `BECBLA0304` | 보증대출 | Guaranteed loans | 2001 | |
| `BECBLA03051` | 일반신용대출 | General unsecured (credit) loans | 2005 | |
| `BECBLA03052` | 집단대출 | **Group loan (중도금/이주비 for pre-sale buyers)** — most causally tied to 분양권 financing | 2005 | ⭐⭐ |
| `BECBLA030201` | 고정형 주택담보대출 | **Fixed-rate mortgage** | 2013 | ⭐ |
| `BECBLA030202` | 변동형 주택담보대출 | **Variable-rate mortgage** | 2013 | ⭐ |
| `BECBLA03041` | 전세자금대출 | **Jeonse (lease-deposit) loan** — 전세 leverage → 갭투자 | 2015 | ⭐ |
| `BECBLA04` | 공공및기타부문대출 | Public & other-sector loans | 1996 | |
| `BECBLA05` | 상업어음할인 | Commercial-bill discount | 1996 | |
| `BECBLA07` | 기업일반자금대출 | Corporate general-purpose loans | 1996 | |

## 121Y015 — 예금은행 대출금리 (잔액 기준) · loan rates, outstanding
Same structure, stock basis (smooth/lagging). Codes `BECBLB*`.

| Item code | 명칭 | Meaning | From |
|---|---|---|---|
| `BECBLB01` | 총대출 | Total loans (avg, outstanding) | 2001 |
| `BECBLB02` | 총대출(당좌대출 제외) | Total loans excl. overdraft | 2001 |
| `BECBLB0201` | 기업대출 | Corporate loans | 2001 |
| `BECBLB020101` | 대기업대출 | Large-enterprise | 2001 |
| `BECBLB020102` | 중소기업대출 | SME | 2001 |
| `BECBLB020103` | 운전자금대출 | Working-capital | 2001 |
| `BECBLB020104` | 시설자금대출 | Facility/capex | 2001 |
| `BECBLB0202` | 가계대출 | Household loans | 2001 |
| `BECBLB020201` | 소액대출 (500만원 이하) | Small loans | 2001 |
| `BECBLB020202` | 주택담보대출 | Mortgage (outstanding) | 2009 |
| `BECBLB020203` | 예·적금담보대출 | Deposit-secured | 2009 |
| `BECBLB020204` | 보증대출 | Guaranteed | 2009 |
| `BECBLB020206` | 일반신용대출 | General credit | 2009 |
| `BECBLB020207` | 집단대출 | Group loan (outstanding) | 2009 |
| `BECBLB020208` | 고정형 주택담보대출 | Fixed-rate mortgage | 2013 |
| `BECBLB020209` | 변동형 주택담보대출 | Variable-rate mortgage | 2013 |
| `BECBLB020210` | 전세자금대출 | Jeonse loan | 2015 |
| `BECBLB03` | 공공및기타부문대출 | Public & other | 2001 |
| `BECBLB04` | 당좌대출 | Overdraft | 1996 |

## 121Y002 — 예금은행 수신금리 (신규취급액 기준) · deposit rates, new business
Funding-side rates. Less directly tied to property, but `저축성수신` is a useful
"cost of money" control. Codes `BEABAA*`.

| Item code | 명칭 | Meaning | From |
|---|---|---|---|
| `BEABAA2` | 저축성수신 | **Savings-type deposits (avg)** — headline deposit rate | 1996 |
| `BEABAA1` | 저축성수신(금융채 제외) | Savings deposits excl. bank debentures | 1996 |
| `BEABAA21` | 순수저축성예금 | Pure savings deposits | 1996 |
| `BEABAA211` | 정기예금 | Time deposit | 1996 |
| `BEABAA2111`–`2117` | 정기예금(만기별) | Time deposit by maturity (<6m, 6m–1y, 1–2y, 2–3y, 3–4y, 4–5y, ≥5y) | 1996 |
| `BEABAA2118` | 정기예금(1년) | Time deposit, 1-year | 2012 |
| `BEABAA212` | 정기적금 | Installment savings | 1996 |
| `BEABAA2121` / `BEABAA2122` | 정기적금(3–4년 / 1–2년) | Installment savings by term | 1996 / 2003 |
| `BEABAA213` | 상호부금 | Mutual installment | 1996 |
| `BEABAA2131` / `BEABAA2132` | 상호부금(3–4년 / 1–2년) | Mutual installment by term | 1996 / 2003 |
| `BEABAA214` | 주택부금 | Housing installment savings | 2000 |
| `BEABAA22` | 시장형금융상품 | Market-type instruments | 1996 |
| `BEABAA221` | 양도성예금증서 | CD (certificate of deposit) | 1996 |
| `BEABAA2211` | 양도성예금증서(91일) | CD, 91-day | 1996 |
| `BEABAA222` | 환매조건부채권매도 | RP (repurchase agreement) | 1996 |
| `BEABAA2221` | 환매조건부채권매도(91–180일) | RP, 91–180 day | 1997 |
| `BEABAA223` | 표지어음 | Cover bill | 1996 |
| `BEABAA2231` | 표지어음(91–120일) | Cover bill, 91–120 day | 1996 |
| `BEABAA224` | 금융채 | Bank debenture | 1996 |

## 121Y013 — 예금은행 수신금리 (잔액 기준) · deposit rates, outstanding
Codes `BEABAB*`.

| Item code | 명칭 | Meaning | From |
|---|---|---|---|
| `BEABAB2` | 총수신(요구불·수시입출식 포함) | Total funding incl. demand & MMDA | 2004 |
| `BEABAB1` | 저축성수신(금융채 제외) | Savings deposits excl. debentures | 2001 |
| `BEABAB21` | 저축성수신(요구불·수시입출식 제외) | Savings excl. demand/MMDA | 2001 |
| `BEABAB211` | 순수저축성예금 | Pure savings deposits | 2001 |
| `BEABAB2111` | 정기예금 | Time deposit | 2001 |
| `BEABAB2112` | 정기적금 | Installment savings | 2001 |
| `BEABAB2113` | 상호부금 | Mutual installment | 2001 |
| `BEABAB2114` | 주택부금 | Housing installment savings | 2001 |
| `BEABAB212` | 시장형금융상품 | Market-type instruments | 2001 |
| `BEABAB2121` | 양도성예금증서 | CD | 2001 |
| `BEABAB2122` | 환매조건부채권매도 | RP | 2001 |
| `BEABAB2123` | 표지어음 | Cover bill | 2001 |
| `BEABAB2124` | 금융채 | Bank debenture | 2001 |
| `BEABAB22` | 수시입출식 저축성예금 | Instant-access savings (MMDA-type) | 2001 |
| `BEABAB221` | 저축예금 | Savings deposit | 1996 |
| `BEABAB2212` | 개인MMDA | Personal MMDA | 1997 |
| `BEABAB222` | 기업자유예금 | Corporate free deposit | 1996 |
| `BEABAB2221` | 기업MMDA | Corporate MMDA | 1997 |
| `BEABAB23` | 요구불예금 | Demand deposit | 2005 |

---

## Recommended additions to the macro feature set
Beyond the current `base_rate` + `mortgage_rate`, the highest-signal 분양권 items:

| Feature name | ECOS code | Why |
|---|---|---|
| `loan_rate_avg` | `121Y006/BECBLA01` | overall weighted-average lending rate (headline macro rate) |
| `group_loan_rate` | `121Y006/BECBLA03052` | 집단대출 — direct financing cost of pre-sale purchase (⭐⭐) |
| `jeonse_loan_rate` | `121Y006/BECBLA03041` | 전세자금대출 — leverage / 갭투자 channel |
| `mortgage_fixed` / `mortgage_var` | `.../BECBLA030201` / `030202` | fixed vs variable mortgage regime |

All monthly, 신규취급액 기준, full 2016+ coverage. Same extractor loop, ~1 call each.
Point-in-time rule (publication lag ~1 month) applies as for existing macro
(see [[ecos-macro-codes]] and docs/realtime_inference.md).

---

## References
- **ECOS 경제통계시스템 (home):** https://ecos.bok.or.kr
- **ECOS OpenAPI guide:** https://ecos.bok.or.kr/api/
- **통계표 경로:** ECOS → 통화·금융 → 금리 → *1.3.3 예금은행 가중평균금리*
  (대출: 121Y006/121Y015, 수신: 121Y002/121Y013); *1.3.4 비은행금융기관* = 121Y004 계열.
- **BOK monthly release:** 한국은행 보도자료 "○월 금융기관 가중평균금리"
  (search "가중평균금리" at https://www.bok.or.kr) — defines methodology & weights.
- Item codes/coverage verified live via `StatisticItemList` on 2026-07-30.
