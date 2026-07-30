"""학교알리미 (schoolinfo.go.kr) extractor — 졸업생 진로현황 (apiType 51) for HS.

Lands per-high-school 학군 signals: school TYPE (특목고/자율고 vs 일반고) + 진학률,
keyed by SCHUL_NM + 법정동. Coordinates are attached later by joining name to the
geocoded NEIS schools (features/school_quality.py) — no separate geocode.

Loops sggCode over the configured region (sidoCode = sgg[:2]). The API serves only
the last ~3 years, so this is a near-static snapshot (documented limitation). Key
via SCHOOLINFO_API_KEY — a separate schoolinfo.go.kr key, never logged.
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from presale.config import get_settings
from presale.features.geocoding import _MERGED_PARENT
from presale.schemas.schoolinfo import SchoolOutcomeRecord

_SUBDIR = "schoolinfo"


@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=1, max=30), reraise=True)
def _get(params: dict[str, str]) -> dict[str, Any]:
    key = get_settings().secrets.schoolinfo_api_key
    if not key:
        raise RuntimeError("SCHOOLINFO_API_KEY is not set.")
    cfg = get_settings().get("sources", "schoolinfo", default={})
    with httpx.Client(follow_redirects=True, timeout=30) as c:
        r = c.get(cfg["base_url"], params={"apiKey": key, **params})
    if not r.is_success:  # never surface the URL (carries the key)
        raise RuntimeError(f"schoolinfo HTTP {r.status_code}")
    return r.json()


def _schoolinfo_sggs(codes: list[str]) -> list[str]:
    """Map merged 부천/화성 구-codes back to their parent 시 code, deduped."""
    return sorted({_MERGED_PARENT.get(c, c) for c in codes})


def extract(regions: list[str] | None = None) -> pd.DataFrame:
    """Fetch HS 졸업생 진로현황 for `regions` (default = full scope). Validated, landed."""
    s = get_settings()
    cfg = s.get("sources", "schoolinfo", default={})
    codes = _schoolinfo_sggs(regions or s.resolve_lawd_codes())

    records: list[SchoolOutcomeRecord] = []
    for sgg in codes:
        j = _get(
            {
                "apiType": cfg["api_type"], "schulKndCode": cfg["school_kind"],
                "sidoCode": sgg[:2], "sggCode": sgg, "pbanYr": str(cfg["pblan_year"]),
            }
        )
        for r in j.get("list") or []:
            try:
                records.append(
                    SchoolOutcomeRecord(
                        school_code=r.get("SCHUL_CODE"),
                        name=r.get("SCHUL_NM"),
                        hs_type=r.get("HS_KND_SC_NM"),
                        grad_rate=r.get("YEAR_GRAD_RATE"),
                        emd_code=r.get("ADRCD_CD"),
                        sigungu_code=sgg,
                    )
                )
            except Exception:  # noqa: BLE001 — skip malformed rows
                continue
        time.sleep(0.1)

    df = pd.DataFrame([r.model_dump() for r in records])
    if not df.empty:
        out = pathlib.Path(s.get("paths", "raw_dir", default="data/raw")) / _SUBDIR
        out.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out / "data.parquet", index=False)
    return df


if __name__ == "__main__":
    d = extract()
    n = d["name"].nunique() if not d.empty else 0
    print(f"schoolinfo: {len(d)} HS rows ({n} schools)")
