"""Parquet landing helpers for the raw lake.

Extractors validate each raw response against its pydantic schema, then land it
as Hive-partitioned Parquet under ``data/raw/<subdir>/region=<code>/`` (local
staging). The storage layer (``gcs.py``) mirrors that tree to GCS, and
``bigquery_io.py`` loads it into the BigQuery ``korea_real_estate.*`` tables that
form the contract with the ML pillar.

No DuckDB: reads happen in BigQuery (cloud) or via pyarrow/pandas (local dev).
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pandas as pd

from data_pipeline.config import get_settings


def init_db() -> None:
    """Create the local raw-lake dirs and (re)build the committed reference table.

    Idempotent (``make setup``). Rebuilds the 법정동 reference parquet from the
    committed txt so a fresh clone has it without any network or warehouse state.
    """
    settings = get_settings()
    for key in ("data_root", "raw_dir", "feature_dir"):
        Path(settings.get("paths", key, default=f"data/{key}")).mkdir(parents=True, exist_ok=True)
    # local import avoids a circular dependency (reference imports refstore, not this)
    from data_pipeline.warehouse.reference import build_legal_dong_table

    try:
        # fetches the 법정동 txt from GCS (or REFERENCE_DIR) and caches it locally
        build_legal_dong_table()
    except Exception as exc:  # noqa: BLE001 — setup is best-effort: warn, don't fail
        logging.getLogger(__name__).warning("skipped reference table build: %s", exc)


def write_region_parquet(df: pd.DataFrame, subdir: str, region: str) -> Path:
    """Write one region's full frame as a SINGLE Parquet file, overwriting cleanly.

    Partitions by region only (Hive dir ``region=<code>/data.parquet``) — one file
    per 시군구 instead of one per region-month, so the lake stays compact. The
    ``region`` column is dropped from the body (it is encoded in the path and
    reconstructed on read via hive partitioning). Returns the file path.
    """
    raw_dir = Path(get_settings().get("paths", "raw_dir", default="data/raw"))
    out = raw_dir / subdir / f"region={region}"
    if out.exists():
        shutil.rmtree(out)  # clean overwrite — never accumulate stale files
    out.mkdir(parents=True, exist_ok=True)
    body = df.drop(columns=["region"], errors="ignore")
    path = out / "data.parquet"
    body.to_parquet(path, index=False)
    return path
