"""NEIS 학교기본정보 extractor -> school amenity reference.

Fetches schools for the configured 교육청 offices (서울 B10 + 경기 J10), paginated,
and lands a single Parquet under data/raw/schools/. NEIS gives 도로명주소 but no
coordinates, so the road address is kept for later geocoding (VWorld ROAD).

The NEIS key sits in the URL query, so this never logs the request URL or an
exception body (which could embed the key). Response envelope is nested:
  {"schoolInfo":[{"head":[{"list_total_count":N},{"RESULT":{...}}]},{"row":[...]}]}
An error/no-data response has no "schoolInfo" key, just {"RESULT":{"CODE":...}}.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from data_pipeline.config import get_settings
from data_pipeline.schemas.school import SchoolRecord

_SUBDIR = "schools"


def _cfg() -> dict[str, Any]:
    return get_settings().get("sources", "neis", default={})


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _get(params: dict[str, str]) -> dict[str, Any]:
    # params carries the key -> never log the URL or the raised error body.
    r = httpx.get(_cfg()["base_url"], params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _parse(payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Return (total_count, rows) from a NEIS schoolInfo payload."""
    info = payload.get("schoolInfo")
    if not info:  # error / no-data envelope
        return 0, []
    total = int(info[0]["head"][0].get("list_total_count") or 0)
    rows = info[1].get("row", [])
    return total, rows


def fetch_office(office_code: str) -> pd.DataFrame:
    """Fetch all schools for one 교육청 office, paginating. Validated rows."""
    cfg = _cfg()
    key = get_settings().secrets.neis_api_key
    if not key:
        raise RuntimeError("NEIS_API_KEY is not set (see .env / .env.example).")
    fields: dict[str, str] = cfg["response_fields"]
    page_size = int(cfg.get("page_size", 1000))

    records: list[dict[str, Any]] = []
    page = 1
    total = None
    while True:
        payload = _get(
            {
                "KEY": key,
                "Type": "json",
                "pIndex": str(page),
                "pSize": str(page_size),
                "ATPT_OFCDC_SC_CODE": office_code,
            }
        )
        total, rows = _parse(payload)
        for row in rows:
            try:
                rec = SchoolRecord(**{dst: row.get(src) for dst, src in fields.items()})
            except Exception:  # noqa: BLE001 — drop schools missing name/address
                continue
            records.append(rec.model_dump())
        if not rows or page >= math.ceil(total / page_size):
            break
        page += 1
    return pd.DataFrame.from_records(records)


def extract() -> pd.DataFrame:
    """Fetch all configured offices and land one schools Parquet. Returns the frame."""
    settings = get_settings()
    offices: list[str] = _cfg().get("office_codes", [])
    if not offices:
        raise RuntimeError("No NEIS office_codes configured (sources.neis.office_codes)")

    frames = [fetch_office(code) for code in offices]
    df = pd.concat([f for f in frames if not f.empty], ignore_index=True)

    raw_dir = Path(settings.get("paths", "raw_dir", default="data/raw"))
    out = raw_dir / _SUBDIR
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "data.parquet", index=False)
    return df


def main() -> None:
    df = extract()
    print(f"NEIS schools: {len(df)} rows")
    if not df.empty:
        print(df["school_type"].value_counts().to_dict())


if __name__ == "__main__":
    main()
