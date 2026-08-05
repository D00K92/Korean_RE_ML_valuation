"""Load the raw Parquet lake into BigQuery — the data<->ML contract boundary.

The data pillar lands raw records as Hive-partitioned Parquet (``parquet_io.py``),
mirrors them to GCS (``gcs.py``), then loads each source into a
``<dataset>.<table>`` BigQuery table here. The ML pillar reads *only* those
tables (``ml_pipeline`` never imports this module and never re-ingests).

Auth is Application Default Credentials (``google.auth.default()`` /
``GOOGLE_APPLICATION_CREDENTIALS``) — never a key value in code. Project, dataset
and location come from ``config.yaml`` (``gcp`` / ``bigquery`` blocks), each
env-overridable (``GCP_PROJECT_ID`` / ``BQ_DATASET``) so deploys don't edit config.
"""

from __future__ import annotations

import logging
import os

from data_pipeline.config import get_settings
from data_pipeline.warehouse.gcs import resolve_bucket

logger = logging.getLogger(__name__)


def _project() -> str | None:
    env = os.environ.get("GCP_PROJECT_ID", "").strip()
    if env:
        return env
    cfg = str(get_settings().get("gcp", "project", default="") or "").strip()
    return cfg or None


def _dataset() -> str:
    env = os.environ.get("BQ_DATASET", "").strip()
    return env or str(get_settings().get("bigquery", "dataset", default="korea_real_estate"))


def _location() -> str:
    return str(get_settings().get("bigquery", "location", default="asia-northeast3"))


def table_for(source: str) -> str:
    """Map a raw-lake source subdir (e.g. ``molit_resale``) to its BQ table name."""
    tables = get_settings().get("bigquery", "tables", default={}) or {}
    return str(tables.get(source, source))


def dataset_ref() -> str:
    """``project.dataset`` (or ``dataset`` when project falls back to ADC default)."""
    project = _project()
    return f"{project}.{_dataset()}" if project else _dataset()


def table_ref(source: str) -> str:
    """Fully-qualified ``[project.]dataset.table`` for a raw-lake source."""
    return f"{dataset_ref()}.{table_for(source)}"


def _client():
    from google.cloud import bigquery

    return bigquery.Client(project=_project())


def ensure_dataset() -> str:
    """Create the contract dataset if missing (idempotent). Returns its ref."""
    from google.cloud import bigquery

    client = _client()
    ds = bigquery.Dataset(dataset_ref())
    ds.location = _location()
    client.create_dataset(ds, exists_ok=True)
    logger.info("ensured BigQuery dataset %s (%s)", dataset_ref(), _location())
    return dataset_ref()


def load_source_from_gcs(
    source: str,
    *,
    table: str | None = None,
    write_disposition: str = "WRITE_TRUNCATE",
) -> int:
    """Load ``gs://<bucket>/<raw_prefix>/<source>/`` Parquet into BigQuery.

    Uses Hive partitioning (``AUTO``) so the ``region=<code>`` path segment is
    reconstructed as a ``region`` column (it is dropped from the Parquet body on
    landing). ``WRITE_TRUNCATE`` makes each load a full replace, which reconciles
    late reports / 해제 (cancellations) exactly like the local lake overwrite.
    Returns the resulting table row count.
    """
    from google.cloud import bigquery

    bucket = resolve_bucket()
    raw_prefix = str(get_settings().get("gcs", "raw_prefix", default="raw")).strip("/")
    uri_prefix = f"gs://{bucket}/{raw_prefix}/{source}/"
    source_uris = f"{uri_prefix}*"

    hive = bigquery.HivePartitioningOptions()
    hive.mode = "AUTO"
    hive.source_uri_prefix = uri_prefix
    hive.require_partition_filter = False

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=write_disposition,
        hive_partitioning=hive,
        autodetect=True,
    )

    client = _client()
    ensure_dataset()
    target = table or table_ref(source)
    job = client.load_table_from_uri(source_uris, target, job_config=job_config)
    job.result()  # wait for completion; raises on failure
    rows = client.get_table(target).num_rows
    logger.info("loaded %s -> %s (%d rows)", source_uris, target, rows)
    return int(rows)


def load_lake_to_bigquery(sources: list[str]) -> dict[str, int]:
    """Load each source's GCS Parquet into its BigQuery table. Returns {source: rows}."""
    ensure_dataset()
    out: dict[str, int] = {}
    for source in sources:
        out[source] = load_source_from_gcs(source)
    return out
