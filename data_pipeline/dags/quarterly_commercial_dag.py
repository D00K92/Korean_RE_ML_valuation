"""Airflow DAG — quarterly ingest of the 상가(상권)정보 amenity source.

소상공인시장진흥공단 refreshes the 상가업소 dataset each 분기, so this runs on the 1st
of Jan/Apr/Jul/Oct. Feeds spatial amenity features; the downstream ML training +
eval pipeline (Kubeflow) picks up whatever has landed.

    extract_commercial ─▶ audit_row_counts ─▶ upload_raw_to_gcs

Uses `commercial.extract(mode="refresh")` so every configured 시군구 is re-pulled
each quarter (overwriting its parquet), rather than the manifest-gated backfill
mode that only fetches missing regions. No business logic here; the task calls the
importable `commercial.extract` (CLAUDE.md).
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

from airflow.decorators import dag, task

# Make the sibling helper importable regardless of Airflow version (2.x adds
# dags/ to sys.path automatically; 3.x does not).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _ingest_common import audit_row_counts, load_raw_to_bigquery, upload_raw_to_gcs  # noqa: E402

DEFAULT_ARGS = {
    "retries": 3,
    "retry_delay": dt.timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

SOURCES = ["commercial"]


@dag(
    dag_id="quarterly_commercial",
    schedule="0 6 1 */3 *",  # 06:00 on the 1st of Jan/Apr/Jul/Oct
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["presale", "ingest", "commercial", "quarterly"],
    doc_md=__doc__,
)
def quarterly_commercial():
    @task
    def extract_commercial() -> str:
        from data_pipeline.ingestion.commercial import extract

        extract(mode="refresh")  # regions=None -> full scope; re-pull every 시군구
        return "commercial"

    extracted = extract_commercial()
    counts = audit_row_counts(SOURCES)
    extracted >> counts
    uploaded = upload_raw_to_gcs(counts)
    uploaded >> load_raw_to_bigquery(counts)  # GCS -> BigQuery contract tables


dag = quarterly_commercial()
