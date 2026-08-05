"""Airflow DAG — monthly ingest of the ECOS (Bank of Korea) macro series.

base_rate / mortgage_rate / M2 / CSI are monthly series (ECOS cycle "M"). Runs on
the 15th, after BOK has published the prior month's figures. The extractor
full-refreshes the whole span each run (~4 API calls, no manifest), so this always
lands a complete, up-to-date wide monthly table.

    extract_ecos ─▶ audit_row_counts ─▶ upload_raw_to_gcs

The downstream ML training + eval pipeline (Kubeflow) consumes the prior month's
macro — always complete by then. No business logic here; the task calls the
importable `ecos.extract` (CLAUDE.md).
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

SOURCES = ["ecos_macro"]


@dag(
    dag_id="monthly_macro",
    schedule="0 6 15 * *",  # 06:00 on the 15th (after BOK's monthly publish)
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["presale", "ingest", "ecos", "monthly"],
    doc_md=__doc__,
)
def monthly_macro():
    @task
    def extract_ecos() -> str:
        from data_pipeline.ingestion.ecos import extract

        extract()
        return "ecos_macro"

    extracted = extract_ecos()
    counts = audit_row_counts(SOURCES)
    extracted >> counts
    uploaded = upload_raw_to_gcs(counts)
    uploaded >> load_raw_to_bigquery(counts)  # GCS -> BigQuery contract tables


dag = monthly_macro()
