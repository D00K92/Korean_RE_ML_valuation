"""ECOS (Bank of Korea) macro extractor -> tidy monthly macro table.

Series (verified live, config/settings.yaml -> sources.ecos.series):
  base_rate     722Y001 / 0101000     한국은행 기준금리 (연%)
  mortgage_rate 121Y006 / BECBLA0302  예금은행 주택담보대출금리 (연리%)
  m2            161Y006 / BBHA00       M2 평잔 원계열 (십억원)
  sentiment_csi 511Y002 / FME          소비자심리지수 (지수)

ECOS is a path-based API: the service key is part of the URL, so this module
never logs the request URL or exception messages (which could embed the key).
Each series is one request covering the whole span (numOfRows high), so a full
backfill is ~4 calls — no manifest / incremental machinery needed.

Point-in-time note: base_rate is known same-day, but M2 / mortgage / CSI publish
with a ~1 month lag. Availability lag is applied in the FEATURE layer (join macro
as-of prediction_date), not here — ingestion just lands the raw monthly values.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from presale.config import get_settings
from presale.schemas.ecos import EcosObservation

_SUBDIR = "ecos_macro"


def _cfg() -> dict[str, Any]:
    return get_settings().get("sources", "ecos", default={})


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _get(url: str) -> dict[str, Any]:
    # NOTE: `url` embeds the service key — never log it or the raised error body.
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_series(name: str, spec: dict[str, str], start_ym: str, end_ym: str) -> pd.DataFrame:
    """Fetch one ECOS series over [start_ym, end_ym]. Returns validated long rows."""
    cfg = _cfg()
    key = get_settings().secrets.ecos_api_key
    if not key:
        raise RuntimeError("ECOS_API_KEY is not set (see .env / .env.example).")
    base = cfg["base_url"]
    cycle = cfg.get("cycle", "M")
    stat, item = spec["stat_code"], spec.get("item_code", "")

    # end_row generous so the whole span comes back in one page
    url = f"{base}/{key}/json/kr/1/10000/{stat}/{cycle}/{start_ym}/{end_ym}"
    if item:
        url += f"/{item}"

    payload = _get(url)
    if "RESULT" in payload:  # ECOS error envelope (e.g. INFO-200 no data)
        code = payload["RESULT"].get("CODE")
        raise RuntimeError(f"ECOS {name} ({stat}/{item}) returned {code}")

    rows = payload.get("StatisticSearch", {}).get("row", [])
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            obs = EcosObservation(
                series=name,
                deal_ym=row.get("TIME"),
                value=row.get("DATA_VALUE"),
                unit=row.get("UNIT_NAME"),
            )
        except Exception:  # noqa: BLE001 — skip malformed / suppressed values
            continue
        records.append(obs.model_dump())
    return pd.DataFrame.from_records(records)


def extract(start_ym: str | None = None, end_ym: str | None = None) -> pd.DataFrame:
    """Fetch all configured macro series and land ONE wide monthly Parquet.

    Wide table: index deal_ym, one column per series (base_rate, mortgage_rate,
    m2, sentiment_csi). Refetches the full span each run (~4 calls, negligible),
    so there is no incremental/manifest logic.
    """
    settings = get_settings()
    series: dict[str, dict[str, str]] = _cfg().get("series", {})
    if not series:
        raise RuntimeError("No ECOS series configured in settings.yaml sources.ecos.series")

    today = date.today()
    start_ym = start_ym or str(settings.get("ingest", "start_ym", default="202001"))
    end_ym = end_ym or f"{today.year:04d}{today.month:02d}"

    long_frames: list[pd.DataFrame] = []
    for name, spec in series.items():
        df = fetch_series(name, spec, start_ym, end_ym)
        if not df.empty:
            long_frames.append(df)

    if not long_frames:
        return pd.DataFrame()

    long_df = pd.concat(long_frames, ignore_index=True)
    wide = (
        long_df.pivot_table(index="deal_ym", columns="series", values="value")
        .sort_index()
        .reset_index()
    )
    wide.columns.name = None

    raw_dir = Path(settings.get("paths", "raw_dir", default="data/raw"))
    out = raw_dir / _SUBDIR
    out.mkdir(parents=True, exist_ok=True)
    wide.to_parquet(out / "data.parquet", index=False)
    return wide


def main() -> None:
    wide = extract()
    print(f"ECOS macro: {len(wide)} months, columns={list(wide.columns)}")


if __name__ == "__main__":
    main()
