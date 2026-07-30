"""Airflow DAG — daily incremental refresh of the MOLIT 실거래가 lake.

A worked, commented example of the TaskFlow API. It keeps the data lake fresh for
real-time inference by re-fetching each feed's trailing window every day.

Design principle (CLAUDE.md): **the DAG orchestrates, it does not compute.** Every
task is a thin wrapper that imports and calls one importable function from
`src/presale/extract/realtime.py`. No business logic lives in this file — which is
what makes the pipeline testable outside Airflow and portable to any scheduler.

Task graph:

    refresh_label ─┐
                   ├─> write_daily_audit
    refresh_comps ─┘

`refresh_label` runs before `refresh_comps` (they share MOLIT's external rate
limit, so we serialise them rather than let Airflow run them in parallel).
`write_daily_audit` fans in — it runs only after both feeds succeed, and receives
their return values (delta summaries) via **XCom** (Airflow's mechanism for passing
small data between tasks; with TaskFlow you just return a value and accept it as a
function argument).
"""

from __future__ import annotations

import datetime as dt

from airflow.decorators import dag, task

# default_args apply to every task in the DAG.
DEFAULT_ARGS = {
    "retries": 3,                              # MOLIT/data.go.kr time out; retry transient fails
    "retry_delay": dt.timedelta(minutes=5),    # back off between attempts
    "retry_exponential_backoff": True,         # 5m, 10m, 20m — ease off a struggling API
}


@dag(
    dag_id="molit_realtime_refresh",
    schedule="@daily",              # run once a day (early KST, after MOLIT's overnight publish)
    start_date=dt.datetime(2026, 1, 1),
    catchup=False,                  # real-time is FORWARD-only: don't backfill missed days.
                                    # (Historical backfill is the batch pipeline DAG's job.)
    max_active_runs=1,              # never let two daily runs overlap — they'd race on the
                                    # same Parquet partitions + ledger file.
    default_args=DEFAULT_ARGS,
    tags=["molit", "realtime", "ingest"],
    doc_md=__doc__,                 # renders this module docstring in the Airflow UI
)
def molit_realtime_refresh():
    @task
    def refresh_label() -> dict:
        """Re-fetch the 분양권 (label) trailing window; update its first-seen ledger."""
        from presale.extract.realtime import refresh_feed

        return refresh_feed("label")   # returned dict -> XCom (consumed by write_daily_audit)

    @task
    def refresh_comps() -> dict:
        """Re-fetch the 아파트 매매 (comps) trailing window; update its ledger."""
        from presale.extract.realtime import refresh_feed

        return refresh_feed("comps")

    @task
    def write_daily_audit(label_delta: dict, comps_delta: dict) -> str:
        """Fan-in: persist the per-run delta summary (new / cancelled / 등기 counts)."""
        from datetime import date

        from presale.extract.realtime import write_audit

        path = write_audit(date.today(), [label_delta, comps_delta])
        return str(path)

    label = refresh_label()
    comps = refresh_comps()
    
    # serialise: shared MOLIT rate limit
    label >> comps                          
    
    # runs after both; gets their XCom returns
    write_daily_audit(label, comps)         

# run the actual dag.
dag = molit_realtime_refresh()
