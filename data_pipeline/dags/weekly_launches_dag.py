"""Airflow DAG — weekly ingest of the 청약홈 launch sources (event-driven cadence).

Launches (분양정보), their 경쟁률, and the 입주자모집공고문 regulatory PDFs are all
posted as new 공고 happen — roughly weekly, clustered. Each extractor full-refreshes
(re-pulls 2020+/2024+ and overwrites), so a weekly run reliably picks up new
launches. The downstream ML training + eval pipeline (Kubeflow) consumes what lands.

    extract_applyhome ─▶ extract_gonggo ┐
    extract_competition ────────────────┼─▶ audit_row_counts ─▶ upload_raw_to_gcs

gonggo runs after applyhome because `gonggo.list_launches()` prefers the landed
applyhome parquet for its launch universe. No business logic here — tasks call
importable `src` functions (CLAUDE.md).
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

SOURCES = ["applyhome", "applyhome_competition", "gonggo"]


@dag(
    dag_id="weekly_launches",
    schedule="@weekly",
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["presale", "ingest", "applyhome", "weekly"],
    doc_md=__doc__,
)
def weekly_launches():
    @task
    def extract_applyhome() -> str:
        from data_pipeline.ingestion.applyhome import extract

        extract()
        return "applyhome"

    @task
    def extract_competition() -> str:
        from data_pipeline.ingestion.applyhome import extract_competition

        extract_competition()
        return "applyhome_competition"

    @task
    def extract_gonggo() -> str:
        from data_pipeline.ingestion import gonggo

        gonggo.extract(gonggo.list_launches())
        return "gonggo"

    applyhome = extract_applyhome()
    competition = extract_competition()
    gonggo = extract_gonggo()
    applyhome >> gonggo  # gonggo reads the applyhome parquet for its launch list

    counts = audit_row_counts(SOURCES)
    [competition, gonggo] >> counts  # counts after all sources land
    uploaded = upload_raw_to_gcs(counts)
    uploaded >> load_raw_to_bigquery(counts)  # GCS -> BigQuery contract tables


dag = weekly_launches()
