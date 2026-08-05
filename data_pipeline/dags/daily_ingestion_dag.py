"""Airflow DAG — daily incremental refresh of the MOLIT 실거래가 lake.

A worked, commented example of the TaskFlow API. It keeps the data lake fresh for
real-time inference by re-fetching each feed's trailing window every day, then
mirrors the refreshed label + comps parquet to GCS.

Design principle (CLAUDE.md): **the DAG orchestrates, it does not compute.** Every
task is a thin wrapper that imports and calls one importable function from
`data_pipeline/ingestion/realtime.py`. No business logic lives in this file — which is
what makes the pipeline testable outside Airflow and portable to any scheduler.

This DAG is the sole owner of the label (molit_resale) + comps (molit_apt_trade)
sources — both their daily ingest AND their GCS push — so no other DAG re-ingests
or re-uploads them (the per-source ingest DAGs own launches/commercial/macro).

Task graph:

    refresh_label ─┐
                   ├─> write_daily_audit
    refresh_comps ─┴─> audit_row_counts ─> upload_raw_to_gcs

`refresh_label` runs before `refresh_comps` (they share MOLIT's external rate
limit, so we serialise them rather than let Airflow run them in parallel).
`write_daily_audit` fans in — it runs only after both feeds succeed, and receives
their return values (delta summaries) via **XCom** (Airflow's mechanism for passing
small data between tasks; with TaskFlow you just return a value and accept it as a
function argument). `audit_row_counts` -> `upload_raw_to_gcs` then push this DAG's
two sources to the bucket.
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

# default_args apply to every task in the DAG.
DEFAULT_ARGS = {
    "owner": "data-engineer",
    "retries": 3,  # MOLIT/data.go.kr time out; retry transient fails
    "retry_delay": dt.timedelta(minutes=5),  # back off between attempts
    "retry_exponential_backoff": True,  # 5m, 10m, 20m — ease off a struggling API
}

# this DAG's sources — scopes the row audit + GCS upload (never a whole-lake re-push)
SOURCES = ["molit_resale", "molit_apt_trade"]


@dag(
    dag_id="molit_realtime_refresh",
    schedule="@daily",  # run once a day (early KST, after MOLIT's overnight publish)
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,  # real-time is FORWARD-only: don't backfill missed days
    max_active_runs=1,  # never let two daily runs overlap — they'd race on the same partitions
    default_args=DEFAULT_ARGS,
    tags=["molit", "realtime", "ingest"],
    doc_md=__doc__,  # renders this module docstring in the Airflow UI
)
def molit_realtime_refresh():
    @task
    def refresh_label() -> dict:
        """Re-fetch the 분양권 (label) trailing window; update its first-seen ledger."""
        from data_pipeline.ingestion.realtime import refresh_feed

        return refresh_feed("label")  # returned dict -> XCom (consumed by write_daily_audit)

    @task
    def refresh_comps() -> dict:
        """Re-fetch the 아파트 매매 (comps) trailing window; update its ledger."""
        from data_pipeline.ingestion.realtime import refresh_feed

        return refresh_feed("comps")

    @task
    def write_daily_audit(label_delta: dict, comps_delta: dict) -> str:
        """Fan-in: persist the per-run delta summary (new / cancelled / 등기 counts)."""
        from datetime import date

        from data_pipeline.ingestion.realtime import write_audit

        path = write_audit(date.today(), [label_delta, comps_delta])
        return str(path)

    label = refresh_label()
    comps = refresh_comps()
    label >> comps  # serialise: shared MOLIT rate limit

    write_daily_audit(label, comps)  # fan-in delta ledger (runs after both feeds)

    # push this DAG's refreshed sources to GCS (scoped — never the whole lake)
    counts = audit_row_counts(SOURCES)
    comps >> counts
    uploaded = upload_raw_to_gcs(counts)
    uploaded >> load_raw_to_bigquery(counts)  # GCS -> BigQuery contract tables


# run the actual dag.
dag = molit_realtime_refresh()
