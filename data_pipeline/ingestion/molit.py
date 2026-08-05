"""MOLIT 분양권·입주권 전매 실거래가 extractor — the training label source.

Responsibilities:
  - fetch the data.go.kr endpoint per (LAWD_CD, deal year-month)
  - auto-detect encoding (EUC-KR vs UTF-8) with chardet before XML parse
  - retry with backoff (tenacity), respect the configured rate limit
  - map English API keys -> MolitResaleRecord, drop cancelled (해제) rows
  - land Hive-partitioned Parquet (partition by region + deal_ym), incrementally

Incremental strategy (quota discipline — owner is on the ~10k/day default tier):
  - a fetch manifest records EVERY (region, month) pulled, including empties, so
    the ~40% of region-months that return 0 rows are not re-queried next run.
  - a trailing-refresh window always re-fetches the most recent N months even if
    already landed, because MOLIT keeps ingesting late-reported deals for ~30-60
    days — without this the newest months would freeze partial.

This module is import-only business logic; the CLI at the bottom exists so the
Makefile / Airflow can invoke it, but the real entry point is `extract()`.
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

import chardet
import httpx
import pandas as pd
import xmltodict
from tenacity import retry, stop_after_attempt, wait_exponential

from data_pipeline.config import get_settings
from data_pipeline.schemas.molit import MolitResaleRecord
from data_pipeline.warehouse.parquet_io import write_region_parquet

_SUBDIR = "molit_resale"


def _cfg() -> dict[str, Any]:
    return get_settings().get("sources", "molit", default={})


def _url() -> str:
    c = _cfg()
    return f"{c['base_url']}/{c['operation']}"


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _get(params: dict[str, str]) -> bytes:
    r = httpx.get(_url(), params=params, timeout=30)
    r.raise_for_status()
    return r.content


def _decode(raw: bytes) -> str:
    """Decode gov XML bytes, honouring EUC-KR vs UTF-8 (chardet auto-detect)."""
    enc = chardet.detect(raw).get("encoding") or "utf-8"
    try:
        return raw.decode(enc)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("utf-8", errors="replace")


def fetch_month(lawd_cd: str, deal_ym: str) -> pd.DataFrame:
    """Fetch one (region, YYYYMM). Returns validated, non-cancelled rows.

    numOfRows=1000 covers any single region-month for this feed (busiest seen
    was 25 rows), so a single request suffices — no pagination.
    """
    key = get_settings().secrets.molit_api_key
    if not key:
        raise RuntimeError("MOLIT_API_KEY is not set (see .env / .env.example).")

    raw = _get(
        {
            "serviceKey": key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ym,
            "pageNo": "1",
            "numOfRows": "1000",
        }
    )
    parsed = xmltodict.parse(_decode(raw))
    body = parsed.get("response", {}).get("body", {}) or {}
    header = parsed.get("response", {}).get("header", {}) or {}
    if header.get("resultCode") not in ("000", "00"):
        raise RuntimeError(f"MOLIT error {header.get('resultCode')}: {header.get('resultMsg')}")

    items = body.get("items")
    if not items:
        return pd.DataFrame()
    item = items.get("item")
    rows = item if isinstance(item, list) else [item]

    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            rec = MolitResaleRecord(
                region_code=str(row.get("sggCd") or lawd_cd),
                dong=row.get("umdNm"),
                jibun=row.get("jibun"),
                complex_name=row.get("aptNm"),
                exclusive_area_m2=row.get("excluUseAr"),
                floor=row.get("floor"),
                deal_year=row.get("dealYear"),
                deal_month=row.get("dealMonth"),
                deal_day=row.get("dealDay"),
                price_manwon=row.get("dealAmount"),
                right_type=row.get("ownershipGbn"),
                deal_channel=row.get("dealingGbn"),
                is_cancelled=bool(row.get("cdealType")),
            )
        except Exception:  # noqa: BLE001 — bad row (impossible date, missing area) drops
            continue
        if rec.is_cancelled and _cfg().get("exclude_cancelled", True):
            continue
        d = rec.model_dump()
        d["deal_date"] = rec.deal_date
        d["price_per_m2"] = rec.price_per_m2
        d["deal_ym"] = deal_ym
        d["region"] = lawd_cd
        records.append(d)

    return pd.DataFrame.from_records(records)


def _month_range(start_ym: str, end_ym: str) -> list[str]:
    sy, sm = int(start_ym[:4]), int(start_ym[4:])
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    out: list[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _shift_ym(ym: str, delta_months: int) -> str:
    """Add delta_months (may be negative) to a YYYYMM string."""
    idx = int(ym[:4]) * 12 + (int(ym[4:]) - 1) + delta_months
    return f"{idx // 12:04d}{idx % 12 + 1:02d}"


def _raw_dir() -> Path:
    return Path(get_settings().get("paths", "raw_dir", default="data/raw"))


def _region_file(region: str) -> Path:
    """The single Parquet file holding all months for one 시군구."""
    return _raw_dir() / _SUBDIR / f"region={region}" / "data.parquet"


def _read_region_body(region: str) -> pd.DataFrame:
    """Existing landed rows for a region (body only, no `region` col), or empty."""
    path = _region_file(region)
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


# -- fetch manifest: every (region, month) pulled, incl. empties (CSV, sibling of
#    the lake so it is never picked up by the read_parquet('**/*.parquet') glob) --
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
    """Merge pending fetch records into the manifest (latest wins) and persist."""
    if not pending:
        return existing
    path = _manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    combined = pd.concat([existing, pd.DataFrame(pending)], ignore_index=True)
    combined = combined.drop_duplicates(subset=["region", "deal_ym"], keep="last")
    combined.to_csv(path, index=False)
    return combined


_MANIFEST_FLUSH_EVERY = 200  # bound progress loss if a long backfill is interrupted


def extract(mode: Literal["latest", "backfill"] = "latest") -> pd.DataFrame:
    """Extract pooled 분양권+입주권 resale rows for the configured region.

    `backfill` walks start_ym -> present; `latest` covers only the trailing
    refresh window. Skips (region, month) already recorded in the fetch manifest
    unless it falls inside the trailing-refresh window, which is always re-pulled
    (late-reported deals). Lands ONE Parquet file per region (partition by region)
    and returns the combined frame of rows fetched this run.
    """
    settings = get_settings()
    lawd_codes = settings.resolve_lawd_codes()
    if not lawd_codes:
        raise RuntimeError(
            "No region codes resolved. Set region.sido_prefixes (+ reference_file) "
            "or region.lawd_codes in config.yaml."
        )

    today = date.today()
    end_ym = f"{today.year:04d}{today.month:02d}"
    trailing = int(settings.get("ingest", "trailing_refresh_months", default=2) or 0)
    # the trailing window is always re-fetched, in either mode
    refresh_months: set[str] = (
        set(_month_range(_shift_ym(end_ym, -(trailing - 1)), end_ym)) if trailing > 0 else set()
    )

    if mode == "backfill":
        start_ym = str(settings.get("ingest", "start_ym", default="202001"))
    else:  # latest: just the trailing window (or the current month if disabled)
        start_ym = _shift_ym(end_ym, -(trailing - 1)) if trailing > 0 else end_ym
    months = _month_range(start_ym, end_ym)

    qps = float(settings.get("ingest", "rate_limit_qps", default=2) or 2)
    interval = 1.0 / qps if qps > 0 else 0.0

    manifest = load_manifest()
    fetched = _fetched_set()
    pending: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []

    for region in lawd_codes:
        new_frames: list[pd.DataFrame] = []
        refetched: set[str] = set()
        for deal_ym in months:
            is_refresh = deal_ym in refresh_months
            if not is_refresh and (region, deal_ym) in fetched:
                continue  # manifested stable month — skip (incl. known-empties)
            df = fetch_month(region, deal_ym)
            refetched.add(deal_ym)
            if not df.empty:
                new_frames.append(df)
                frames.append(df)
            pending.append(
                {
                    "region": region,
                    "deal_ym": deal_ym,
                    "n_rows": len(df),
                    "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
            if len(pending) >= _MANIFEST_FLUSH_EVERY:
                manifest = _write_manifest(manifest, pending)
                pending = []
            if interval:
                time.sleep(interval)

        # merge this run's rows with already-landed months we didn't refetch,
        # then rewrite the region's single file (one file per 시군구).
        existing = _read_region_body(region)
        if not existing.empty and refetched:
            existing = existing[~existing["deal_ym"].isin(refetched)]
        combined = pd.concat([existing, *new_frames], ignore_index=True)
        if not combined.empty:
            write_region_parquet(combined, _SUBDIR, region)

    _write_manifest(manifest, pending)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser(description="MOLIT 분양권+입주권 resale extractor")
    parser.add_argument("--mode", choices=["latest", "backfill"], default="latest")
    args = parser.parse_args()
    df = extract(mode=args.mode)
    print(f"extracted {len(df)} rows")


if __name__ == "__main__":
    main()
