"""Airflow DAG: extract -> build_features -> train.

TaskFlow API. No business logic lives here — each task imports and calls a
single-purpose function from `src/presale`. Configured with retries +
retry_delay, a schedule interval, and catchup=True for historical backfill.
"""

from __future__ import annotations

import datetime as dt

from airflow.decorators import dag, task

DEFAULT_ARGS = {
    "retries": 3,
    "retry_delay": dt.timedelta(minutes=5),
}


@dag(
    dag_id="presale_pipeline",
    schedule="@monthly",
    start_date=dt.datetime(2020, 1, 1),
    catchup=True,
    default_args=DEFAULT_ARGS,
    tags=["presale", "molit"],
)
def presale_pipeline():
    @task
    def extract() -> str:
        from presale.extract.molit import extract as molit_extract

        molit_extract(mode="backfill")
        return "extracted"

    @task
    def build_features(_upstream: str) -> str:
        from presale.features.build import build_features as build

        build()
        return "features_built"

    @task
    def train(_upstream: str) -> str:
        from presale.train.model import train as train_model

        return train_model()

    train(build_features(extract()))


dag = presale_pipeline()
