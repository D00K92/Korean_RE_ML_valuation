"""소상공인시장진흥공단 상가(상권)정보 extractor -> commercial POI amenity source.

data.go.kr provider B553077 (sdsc2). Uses the data.go.kr account key
(MOLIT_API_KEY). Fetches ALL stores per 시군구 (divId=signguCd) over the
configured scope — coordinates (lat/lon) are included, so NO geocoding needed.

RAW-PASSTHROUGH: every source field is landed untransformed; preprocessing
(coord cast, '' -> null, field selection, 업종 filtering) happens in the feature
layer. High volume (~1M rows), so this PAGINATES and is rollover-safe: a per-
region atomic manifest means hitting the daily quota stops cleanly and a rerun
resumes losslessly. Own lake subdir + manifest (never collides with molit).

부천/화성 note: the 상가 API shares MOLIT's quirk — merged codes 41190/41590 return
NODATA; data is under the 구 codes. resolve_lawd_codes() already yields those.
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from presale.config import get_settings
from presale.storage.duckdb_io import write_region_parquet

_SUBDIR = "commercial"
_PAGE = 1000
_BASE = "http://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"


@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=2, max=40), reraise=True)
def _get(params: dict[str, str]) -> dict[str, Any]:
    r = httpx.get(_BASE, params=params, timeout=40)
    r.raise_for_status()
    text = r.text.strip()
    if not text.startswith("{"):  # 'Forbidden' etc. -> transient, let tenacity retry
        raise RuntimeError("non-JSON response (rate-limited?)")
    return r.json()


def fetch_sigungu(signgu_cd: str) -> pd.DataFrame:
    """Fetch ALL stores for one 시군구 (paginated). Raw passthrough fields."""
    key = get_settings().secrets.molit_api_key
    if not key:
        raise RuntimeError("MOLIT_API_KEY is not set (data.go.kr key).")

    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = _get(
            {
                "serviceKey": key,
                "type": "json",
                "divId": "signguCd",
                "key": signgu_cd,
                "pageNo": str(page),
                "numOfRows": str(_PAGE),
            }
        )
        header = payload.get("header", {})
        code = header.get("resultCode")
        if code == "03":  # NODATA
            break
        if code not in ("00", "0"):
            raise RuntimeError(f"commercial error {code}: {header.get('resultMsg')}")
        body = payload.get("body", {}) or {}
        total = int(body.get("totalCount") or 0)
        items = body.get("items") or []
        all_rows.extend(items)
        if page * _PAGE >= total or not items:
            break
        page += 1

    if not all_rows:
        return pd.DataFrame()
    # raw passthrough: the API mixes int/str in some fields (lnoSlno, bldMnno...),
    # which breaks Parquet. Cast all to nullable string for a uniform raw layer
    # (preprocessing re-types lat/lon later).
    df = pd.DataFrame(all_rows).astype("string")
    df["region"] = signgu_cd
    return df


# -- manifest (own file, sibling of the commercial lake) --
def _raw_dir() -> Path:
    return Path(get_settings().get("paths", "raw_dir", default="data/raw"))


def _manifest_path() -> Path:
    return _raw_dir() / f"{_SUBDIR}_fetch_manifest.csv"


def load_manifest() -> pd.DataFrame:
    p = _manifest_path()
    if p.exists():
        return pd.read_csv(p, dtype={"region": str})
    return pd.DataFrame(columns=["region", "n_rows", "fetched_at"])


def _fetched_set() -> set[str]:
    return set(load_manifest()["region"])


def _write_manifest(existing: pd.DataFrame, pending: list[dict[str, Any]]) -> pd.DataFrame:
    if not pending:
        return existing
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([existing, pd.DataFrame(pending)], ignore_index=True)
    combined = combined.drop_duplicates(subset=["region"], keep="last")
    combined.to_csv(p, index=False)
    return combined


def extract(regions: list[str] | None = None) -> pd.DataFrame:
    """Backfill raw commercial POIs for `regions` (default = full configured scope).

    One Parquet file per 시군구. Rollover-safe: a 시군구 is written then manifested
    atomically, so a quota stop mid-run resumes losslessly on rerun.
    """
    settings = get_settings()
    if regions is None:
        regions = settings.resolve_lawd_codes()

    qps = float(settings.get("ingest", "rate_limit_qps", default=2) or 2)
    interval = 1.0 / qps if qps > 0 else 0.0

    manifest = load_manifest()
    fetched = _fetched_set()
    frames: list[pd.DataFrame] = []
    stopped_at: str | None = None

    for region in regions:
        if region in fetched:
            continue
        try:
            df = fetch_sigungu(region)
        except Exception as exc:  # noqa: BLE001 — retries exhausted (likely quota)
            stopped_at = f"region={region}: {type(exc).__name__}: {exc}"
            break
        if not df.empty:
            write_region_parquet(df, _SUBDIR, region)
            frames.append(df)
        manifest = _write_manifest(
            manifest,
            [{"region": region, "n_rows": len(df),
              "fetched_at": datetime.now(UTC).isoformat(timespec="seconds")}],
        )
        if interval:
            time.sleep(interval)

    if stopped_at:
        done = manifest["region"].nunique() if not manifest.empty else 0
        print(f"STOPPED early at {stopped_at}\n  completed {done} 시군구; rerun to resume")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description="상가(상권)정보 commercial extractor")
    parser.add_argument("--regions", nargs="*", help="signguCd list (default: full scope)")
    args = parser.parse_args()
    df = extract(regions=args.regions)
    print(f"commercial: fetched {len(df)} rows this run")


if __name__ == "__main__":
    main()
