"""청약홈 분양정보 -> feature enrichment for MOLIT label rows (and inference rows).

Attaches launch-time-fixed attributes from a 청약홈 announcement to each 분양권
resale row, matched by base_name + 시도, with the hard leakage guard that the
announcement's 공고일 must be <= the row's deal_date (CLAUDE.md invariant #3).

Emitted features (all null-safe; unmatched rows stay NaN, LightGBM handles it):
  ah_supply_price_per_m2  분양가 만원/㎡  (launch base price — NOT the label)
  ah_months_to_completion 입주예정 - deal_date, in months (marquee 분양권 driver)
  ah_total_units          단지 규모
  ah_builder              건설사 (brand proxy)
  ah_matched / ah_pblanc_no / ah_notice_date  (audit + leakage test)
When raw 경쟁률 is supplied, also (demand signal, ρ=0.277 with premium):
  ah_competition_rate     총접수 / 공급세대
  ah_undersubscribed      미달 (rate < 1) — 마이너스-프리미엄 risk
  ah_rank1_local_rate     1순위 해당지역 rate
  ah_local_demand_share   해당지역 접수 / 총 접수

NOTE: a ratio like resale_price / 분양가 is deliberately NOT produced — it divides
by the label and would be target leakage. 분양가 enters as a standalone feature;
the model learns premium implicitly with resale price as the target.
"""

from __future__ import annotations

import pandas as pd

from presale.features.geocoding import base_name

# 청약홈 SUBSCRPT_AREA_CODE_NM -> 시도 code prefix (region.sido_prefixes)
_REGION_TO_SIDO = {
    "서울": "11", "경기": "41", "인천": "28", "부산": "26", "대구": "27",
    "대전": "30", "광주": "29", "울산": "31", "세종": "36",
}


def _sido(region_code: object) -> str:
    return str(region_code)[:2]


def build_applyhome_index(
    applyhome: pd.DataFrame,
) -> dict[tuple[str, str], list[dict]]:
    """(시도, base_name(house_name)) -> list of per-주택형 records for matching."""
    idx: dict[tuple[str, str], list[dict]] = {}
    for r in applyhome.itertuples(index=False):
        sido = _REGION_TO_SIDO.get(getattr(r, "supply_region", None), "")
        key = (sido, base_name(getattr(r, "house_name", "")))
        if not key[0] or not key[1]:
            continue
        idx.setdefault(key, []).append(
            {
                "area": getattr(r, "exclusive_area_m2", None),
                "price_manwon": getattr(r, "supply_price_manwon", None),
                "notice_date": pd.Timestamp(r.notice_date),
                "move_in_ym": getattr(r, "move_in_ym", None),
                "total_units": getattr(r, "total_units", None),
                "builder": getattr(r, "builder", None),
                "pblanc_no": getattr(r, "pblanc_no", None),
            }
        )
    return idx


def _months_to_completion(move_in_ym: object, deal_date: pd.Timestamp) -> float | None:
    if not move_in_ym or pd.isna(deal_date):
        return None
    s = str(move_in_ym)
    if len(s) < 6 or not s[:6].isdigit():
        return None
    y, m = int(s[:4]), int(s[4:6])
    return (y - deal_date.year) * 12 + (m - deal_date.month)


def _best_match(cands: list[dict], deal_date: pd.Timestamp, area: float | None) -> dict | None:
    """Among candidates with 공고일 <= deal_date, pick closest 전용면적 then latest 공고."""
    ok = [c for c in cands if c["notice_date"] <= deal_date]  # LEAKAGE GUARD
    if not ok:
        return None
    if area is None:
        return max(ok, key=lambda c: c["notice_date"])
    return min(ok, key=lambda c: (abs((c["area"] or 0) - area), -c["notice_date"].value))


# -- 청약 경쟁률 (demand) --------------------------------------------------
_COMP_COLS = [
    "ah_competition_rate", "ah_undersubscribed",
    "ah_rank1_local_rate", "ah_local_demand_share",
]


def aggregate_competition(raw: pd.DataFrame) -> pd.DataFrame:
    """Collapse the (순위 × 거주지역) 경쟁률 rows to per-(PBLANC_NO, 전용면적) metrics.

    We compute the rate from 접수(REQ_CNT)/공급(SUPLY_HSHLDCO) rather than parse the
    CMPET_RATE string (30% is 미달 '(△N)', ~half is '-'). 전용면적 comes from the
    HOUSE_TY leading number, rounded to int for a robust label join.
    """
    cols = ["pblanc_no", "area", *_COMP_COLS]
    if raw.empty:
        return pd.DataFrame(columns=cols)
    d = raw.copy()
    d["req"] = pd.to_numeric(d["REQ_CNT"], errors="coerce").fillna(0)
    d["sup"] = pd.to_numeric(d["SUPLY_HSHLDCO"], errors="coerce")
    d["area"] = d["HOUSE_TY"].astype(str).str.extract(r"([\d.]+)")[0].astype(float).round(0)
    d["rank"] = pd.to_numeric(d["SUBSCRPT_RANK_CODE"], errors="coerce")
    d["local"] = d["RESIDE_SENM"].astype(str).eq("해당지역")
    d = d.dropna(subset=["area"])

    keys = ["PBLANC_NO", "area"]
    agg = d.groupby(keys).agg(total_req=("req", "sum"), supply=("sup", "max")).reset_index()
    local = d[d["local"]].groupby(keys)["req"].sum().rename("local_req")
    r1l = d[(d["rank"] == 1) & d["local"]].groupby(keys)["req"].sum().rename("rank1_local_req")
    agg = agg.merge(local, on=keys, how="left").merge(r1l, on=keys, how="left")
    agg[["local_req", "rank1_local_req"]] = agg[["local_req", "rank1_local_req"]].fillna(0)
    agg = agg[agg["supply"] > 0].copy()

    agg["ah_competition_rate"] = agg["total_req"] / agg["supply"]
    agg["ah_undersubscribed"] = agg["ah_competition_rate"] < 1
    agg["ah_rank1_local_rate"] = agg["rank1_local_req"] / agg["supply"]
    agg["ah_local_demand_share"] = (agg["local_req"] / agg["total_req"]).where(agg["total_req"] > 0)
    return agg.rename(columns={"PBLANC_NO": "pblanc_no"})[cols]


def build_competition_index(agg: pd.DataFrame) -> dict[tuple[str, float], dict]:
    """(pblanc_no, rounded 전용면적) -> competition metrics."""
    return {
        (str(r.pblanc_no), float(r.area)): {c: getattr(r, c) for c in _COMP_COLS}
        for r in agg.itertuples(index=False)
    }


def enrich_labels(
    labels: pd.DataFrame,
    applyhome: pd.DataFrame,
    competition: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return `labels` with the ah_* enrichment columns appended (null-safe).

    If `competition` (raw 경쟁률) is given, also attach demand features, joined on
    (matched PBLANC_NO, 전용면적). Same leakage position: subscription precedes resale.
    """
    idx = build_applyhome_index(applyhome)
    comp_idx = (
        build_competition_index(aggregate_competition(competition))
        if competition is not None else None
    )
    out = labels.copy()
    out["deal_dt"] = pd.to_datetime(out["deal_date"], errors="coerce")

    rows: list[dict] = []
    for row in out.itertuples(index=False):
        key = (_sido(row.region_code), base_name(getattr(row, "complex_name", "")))
        area = getattr(row, "exclusive_area_m2", None)
        best = _best_match(idx.get(key, []), row.deal_dt, area)
        if best is None:
            rows.append({"ah_matched": False})
            continue
        a = best["area"]
        rec = {
            "ah_supply_price_per_m2": (best["price_manwon"] / a if a else None),
            "ah_months_to_completion": _months_to_completion(best["move_in_ym"], row.deal_dt),
            "ah_total_units": best["total_units"],
            "ah_builder": best["builder"],
            "ah_matched": True,
            "ah_pblanc_no": best["pblanc_no"],
            "ah_notice_date": best["notice_date"],
        }
        if comp_idx is not None:
            hit = comp_idx.get((str(best["pblanc_no"]), round(a)) if a else None)
            rec.update(hit or dict.fromkeys(_COMP_COLS))
        rows.append(rec)

    base_cols = [
        "ah_supply_price_per_m2", "ah_months_to_completion", "ah_total_units",
        "ah_builder", "ah_matched", "ah_pblanc_no", "ah_notice_date",
    ]
    cols = base_cols + (_COMP_COLS if comp_idx is not None else [])
    enriched = pd.DataFrame(rows, index=out.index).reindex(columns=cols)
    enriched["ah_matched"] = enriched["ah_matched"].fillna(False)
    return pd.concat([out.drop(columns=["deal_dt"]), enriched], axis=1)
