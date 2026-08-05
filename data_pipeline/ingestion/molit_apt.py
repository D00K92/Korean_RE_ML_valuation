"""MOLIT 아파트 매매 실거래가 extractor -> COMP feature source (not the label).

Same MOLIT gateway/key as the 분양권 label feed, different endpoint
(getRTMSDataSvcAptTrade). These are sales of COMPLETED apartments, used to build
comparable-sales features for each 분양권 row (invariant #1: comps are lagged to
reporting delay and never leak past prediction_date — enforced in the feature
layer, not here).

RAW-PASSTHROUGH: every source field is landed untransformed (strings as-is), by
owner request — preprocessing (units, floor, renames, dedup) is decided later and
applied in the feature layer. Only region/deal_ym partition keys are added.

Higher volume than the 분양권 feed, so this PAGINATES per (region, month). Uses
its own lake subdir + manifest so it never collides with molit_resale.
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import xmltodict
from tenacity import retry, stop_after_attempt, wait_exponential

from data_pipeline.config import get_settings
from data_pipeline.ingestion.molit import _decode, _month_range, _shift_ym
from data_pipeline.warehouse.parquet_io import write_region_parquet

_SUBDIR = "molit_apt_trade"
_PAGE = 1000


def _cfg() -> dict[str, Any]:
    # apt-trade lives under the molit source's `fallback` block in settings.yaml
    return get_settings().get("sources", "molit", "fallback", default={})


def _url() -> str:
    c = _cfg()
    base = c.get("base_url", "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade")
    op = c.get("operation", "getRTMSDataSvcAptTrade")
    return f"{base}/{op}"


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _get(params: dict[str, str]) -> bytes:
    r = httpx.get(_url(), params=params, timeout=30)
    r.raise_for_status()
    return r.content


def fetch_month(lawd_cd: str, deal_ym: str) -> pd.DataFrame:
    """Fetch ALL apartment sales for one (region, YYYYMM), paginating. Raw fields."""
    key = get_settings().secrets.molit_api_key
    if not key:
        raise RuntimeError("MOLIT_API_KEY is not set (see .env / .env.example).")

    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        raw = _get(
            {
                "serviceKey": key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ym,
                "pageNo": str(page),
                "numOfRows": str(_PAGE),
            }
        )
        parsed = xmltodict.parse(_decode(raw))
        resp = parsed.get("response", {})
        header = resp.get("header", {}) or {}
        if header.get("resultCode") not in ("000", "00"):
            code, msg = header.get("resultCode"), header.get("resultMsg")
            raise RuntimeError(f"apt-trade error {code}: {msg}")
        body = resp.get("body", {}) or {}
        total = int(body.get("totalCount") or 0)
        items = body.get("items")
        if items:
            item = items.get("item")
            rows = item if isinstance(item, list) else [item]
            all_rows.extend(rows)
        if page * _PAGE >= total or not items:
            break
        page += 1

    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)  # raw passthrough — all source columns, as strings
    df["region"] = lawd_cd
    df["deal_ym"] = deal_ym
    return df


# -- manifest (own file, sibling of the apt-trade lake) --
def _raw_dir() -> Path:
    return Path(get_settings().get("paths", "raw_dir", default="data/raw"))


def _manifest_path() -> Path:
    return _raw_dir() / f"{_SUBDIR}_fetch_manifest.csv"


def load_manifest() -> pd.DataFrame:
    path = _manifest_path()
    if path.exists():
        return pd.read_csv(path, dtype={"region": str, "deal_ym": str})
    return pd.DataFrame(columns=["region", "deal_ym", "n_rows", "fetched_at"])


def _fetched_set() -> set[tuple[str, str]]:
    m = load_manifest()
    return set(zip(m["region"], m["deal_ym"], strict=False))


def _write_manifest(existing: pd.DataFrame, pending: list[dict[str, Any]]) -> pd.DataFrame:
    if not pending:
        return existing
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([existing, pd.DataFrame(pending)], ignore_index=True)
    combined = combined.drop_duplicates(subset=["region", "deal_ym"], keep="last")
    combined.to_csv(path, index=False)
    return combined


def _region_file(region: str) -> Path:
    return _raw_dir() / _SUBDIR / f"region={region}" / "data.parquet"


def _read_region_body(region: str) -> pd.DataFrame:
    path = _region_file(region)
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def extract(regions: list[str] | None = None, mode: str = "backfill") -> pd.DataFrame:
    """Backfill raw apt-trade for `regions` (default = full configured scope)."""
    settings = get_settings()
    if regions is None:
        regions = settings.resolve_lawd_codes()

    today = date.today()
    end_ym = f"{today.year:04d}{today.month:02d}"
    trailing = int(settings.get("ingest", "trailing_refresh_months", default=2) or 0)
    refresh_months = (
        set(_month_range(_shift_ym(end_ym, -(trailing - 1)), end_ym)) if trailing > 0 else set()
    )
    start_ym = (
        str(settings.get("ingest", "start_ym", default="201601"))
        if mode == "backfill"
        else (_shift_ym(end_ym, -(trailing - 1)) if trailing > 0 else end_ym)
    )
    months = _month_range(start_ym, end_ym)

    qps = float(settings.get("ingest", "rate_limit_qps", default=2) or 2)
    interval = 1.0 / qps if qps > 0 else 0.0

    manifest = load_manifest()
    fetched = _fetched_set()
    frames: list[pd.DataFrame] = []
    stopped_at: str | None = None

    for region in regions:
        new_frames: list[pd.DataFrame] = []
        refetched: set[str] = set()
        region_pending: list[dict[str, Any]] = []
        try:
            for deal_ym in months:
                if deal_ym not in refresh_months and (region, deal_ym) in fetched:
                    continue
                df = fetch_month(region, deal_ym)
                refetched.add(deal_ym)
                if not df.empty:
                    new_frames.append(df)
                region_pending.append(
                    {
                        "region": region,
                        "deal_ym": deal_ym,
                        "n_rows": len(df),
                        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    }
                )
                if interval:
                    time.sleep(interval)
        except Exception as exc:  # noqa: BLE001
            # tenacity already exhausted retries -> persistent failure, most
            # likely the daily quota. Stop cleanly: DO NOT write or manifest this
            # region, so it is fully refetched on resume (no phantom "fetched").
            stopped_at = f"region={region} (~{deal_ym}): {type(exc).__name__}: {exc}"
            break

        # region fully fetched: write its file, THEN record the manifest, so the
        # two never disagree if a later region is interrupted.
        existing = _read_region_body(region)
        if not existing.empty and refetched:
            existing = existing[~existing["deal_ym"].isin(refetched)]
        combined = pd.concat([existing, *new_frames], ignore_index=True)
        if not combined.empty:
            write_region_parquet(combined, _SUBDIR, region)
        manifest = _write_manifest(manifest, region_pending)
        frames.extend(new_frames)

    if stopped_at:
        done = manifest["region"].nunique() if not manifest.empty else 0
        print(f"STOPPED early at {stopped_at}\n  completed regions saved ({done}); rerun to resume")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description="MOLIT apartment-trade (comp) extractor")
    parser.add_argument("--regions", nargs="*", help="LAWD_CD list (default: full scope)")
    args = parser.parse_args()
    df = extract(regions=args.regions)
    print(f"apt-trade: fetched {len(df)} rows")


if __name__ == "__main__":
    main()
