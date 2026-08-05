"""청약홈 분양정보 extractor — feature ENRICHMENT source (train + inference).

Pulls the 한국부동산원 청약홈 분양정보 API (odcloud, ApplyhomeInfoDetailSvc),
joins announcement-level detail to per-주택형 model rows on PBLANC_NO, filters to
수도권, and lands one validated table. Data spans 2020+ (청약홈 platform era).

Used to enrich BOTH training and inference per CLAUDE.md invariant #3 (rev
2026-07-29) with launch-time fields only. The 공고일 <= deal_date leakage guard is
applied at join time in features/enrich.py, not here.

Key handling: odcloud accepts the data.go.kr ACCOUNT key. We prefer a dedicated
APPLYHOME_API_KEY but fall back to MOLIT_API_KEY (same account). Keys never logged.
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from data_pipeline.config import get_settings
from data_pipeline.schemas.applyhome import ApplyhomeRecord

_SUBDIR = "applyhome"


def _key() -> str:
    s = get_settings().secrets
    key = s.applyhome_api_key or s.molit_api_key  # same data.go.kr account
    if not key:
        raise RuntimeError("No data.go.kr key (APPLYHOME_API_KEY / MOLIT_API_KEY).")
    return key


@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    r = httpx.get(url, params=params, timeout=40)
    if not r.is_success:  # never surface the URL (carries the key)
        raise RuntimeError(f"applyhome HTTP {r.status_code}")
    return r.json()


def _pull_url(url: str) -> list[dict[str, Any]]:
    """Page through an odcloud endpoint fully (perPage=1000)."""
    key, out, page = _key(), [], 1
    while True:
        j = _get(url, {"page": page, "perPage": 1000, "serviceKey": key})
        out.extend(j.get("data") or [])
        if page * 1000 >= (j.get("totalCount") or 0):
            break
        page += 1
        time.sleep(0.15)
    return out


def _pull_all(operation: str) -> list[dict[str, Any]]:
    cfg = get_settings().get("sources", "applyhome", default={})
    return _pull_url(f"{cfg['base_url']}/{operation}")


def extract() -> pd.DataFrame:
    """Fetch + join 수도권 분양정보, validate, land to data/raw/applyhome/data.parquet."""
    s = get_settings()
    cfg = s.get("sources", "applyhome", default={})
    regions = set(cfg.get("region_names", ["서울", "경기", "인천"]))

    detail = _pull_all(cfg["operations"]["apt_detail"])
    model = _pull_all(cfg["operations"]["apt_model"])
    # Land ALL 수도권 announcements untransformed — every housing kind the APT feed
    # returns (APT + 신혼희망타운 + 민간사전청약, all apartment-type). Housing-kind
    # selection is left to preprocessing/feature-eng via the `house_kind` column,
    # not hard-filtered here (raw stays auditable; see CLAUDE.md storage convention).
    det = {d["PBLANC_NO"]: d for d in detail if d.get("SUBSCRPT_AREA_CODE_NM") in regions}

    records: list[ApplyhomeRecord] = []
    for m in model:
        d = det.get(m.get("PBLANC_NO"))
        if d is None:
            continue
        try:
            records.append(
                ApplyhomeRecord(
                    pblanc_no=str(d["PBLANC_NO"]),
                    house_name=d["HOUSE_NM"],
                    house_kind=d.get("HOUSE_SECD_NM"),
                    supply_region=d.get("SUBSCRPT_AREA_CODE_NM"),
                    address=d.get("HSSPLY_ADRES"),
                    notice_date=d["RCRIT_PBLANC_DE"],
                    move_in_ym=(str(d["MVN_PREARNGE_YM"]) if d.get("MVN_PREARNGE_YM") else None),
                    total_units=d.get("TOT_SUPLY_HSHLDCO"),
                    builder=d.get("CNSTRCT_ENTRPS_NM"),
                    house_type=m["HOUSE_TY"],
                    exclusive_area_m2=m["HOUSE_TY"],  # validator parses the leading number
                    supply_price_manwon=m["LTTOT_TOP_AMOUNT"],
                )
            )
        except Exception:  # noqa: BLE001 — skip malformed 주택형 rows (e.g. blank price)
            continue

    df = pd.DataFrame([r.model_dump() for r in records])
    if not df.empty:
        out = pathlib.Path(s.get("paths", "raw_dir", default="data/raw")) / _SUBDIR
        out.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out / "data.parquet", index=False)
    return df


def extract_competition() -> pd.DataFrame:
    """Land raw 청약 경쟁률 (nationwide, untransformed) to data/raw/applyhome_competition/.

    Raw passthrough (all cols -> nullable string; the feed mixes int/str). The
    수도권 restriction + per-주택형 aggregation happen downstream in features/enrich.py
    (the label join naturally drops non-수도권 PBLANCs). See docs/applyhome_features.md.
    """
    s = get_settings()
    cfg = s.get("sources", "applyhome", "competition", default={})
    rows = _pull_url(f"{cfg['base_url']}/{cfg['operation']}")
    df = pd.DataFrame(rows).astype("string")
    if not df.empty:
        out = pathlib.Path(s.get("paths", "raw_dir", default="data/raw")) / cfg["raw_subdir"]
        out.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out / "data.parquet", index=False)
    return df


if __name__ == "__main__":
    d = extract()
    n = d["pblanc_no"].nunique() if not d.empty else 0
    print(f"applyhome: {len(d)} 주택형 rows across {n} 공고")
