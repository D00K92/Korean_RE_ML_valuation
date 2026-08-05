"""Shared TaskFlow tasks for the ingest DAGs — audit + scoped GCS upload + BQ load.

Kept out of the individual DAG files so the weekly / quarterly / monthly ingest
pipelines don't each re-declare the same wrappers. Orchestration-only: the real
logic lives in `data_pipeline.warehouse` (`dataset_row_counts`, `sync_to_gcs`,
`load_lake_to_bigquery`).

Every task is *scoped* to the sources a given DAG ingested, so e.g. the weekly
launches DAG never re-audits/re-uploads/re-loads the multi-million-row apt-trade
lake it did not touch. Each ingest DAG runs audit -> upload_raw_to_gcs ->
load_raw_to_bigquery, landing a fresh, GCS-mirrored, BigQuery-loaded contract for
the Vertex AI ML pipeline. Airflow puts the `dags/` folder on `sys.path`, so DAG
files import these as `from _ingest_common import ...`.
"""

from __future__ import annotations

import logging

from airflow.decorators import task

log = logging.getLogger("airflow.task")


@task
def audit_row_counts(sources: list[str]) -> dict[str, int]:
    """Rows per dataset (Parquet footer counts) for this DAG's `sources`.

    Logs one line per source (+ TOTAL) and returns the mapping via XCom, so each
    run records how many rows actually landed per dataset.
    """
    from data_pipeline.warehouse.lake import dataset_row_counts

    all_counts = dataset_row_counts()
    counts = {s: all_counts.get(s, 0) for s in sources}
    for source, n in counts.items():
        log.info("rowcount  %-22s %12d", source, n)
    log.info("rowcount  %-22s %12d", "TOTAL", sum(counts.values()))
    return counts


@task
def upload_raw_to_gcs(counts: dict[str, int]) -> str:
    """Mirror only the audited source subdirs to gs://<bucket>/<raw_prefix>/<source>.

    Scoped per source (via `sync_to_gcs(local_dir=..., prefix=...)`) so a DAG only
    pushes what it ingested. Sources with no local dir are skipped, not fatal.
    """
    from data_pipeline.config import PROJECT_ROOT, get_settings
    from data_pipeline.warehouse.gcs import sync_to_gcs

    s = get_settings()
    raw_dir = PROJECT_ROOT / str(s.get("paths", "raw_dir", default="data/raw"))
    raw_prefix = str(s.get("gcs", "raw_prefix", default="raw"))

    total_files, uploaded = 0, []
    for source in counts:
        sub = raw_dir / source
        if not sub.exists():
            log.warning("skip upload: %s has no local dir (%s)", source, sub)
            continue
        uris = sync_to_gcs(local_dir=sub, prefix=f"{raw_prefix}/{source}")
        total_files += len(uris)
        uploaded.append(source)

    rows = sum(counts.values())
    return f"uploaded {total_files} file(s) for {len(uploaded)} dataset(s), {rows:,} rows"


@task
def load_raw_to_bigquery(counts: dict[str, int]) -> str:
    """Load this DAG's audited sources from GCS into their BigQuery tables.

    Closes the ingest contract: after the parquet is mirrored to GCS, each source
    is loaded (WRITE_TRUNCATE, Hive-partitioned) into ``<dataset>.<table>`` so the
    Vertex AI ML pipeline reads a fresh warehouse. Scoped to sources that actually
    landed rows; empty sources are skipped, not fatal.
    """
    from data_pipeline.warehouse.bigquery_io import load_lake_to_bigquery, table_ref

    sources = [s for s, n in counts.items() if n > 0]
    if not sources:
        log.warning("no non-empty sources to load into BigQuery")
        return "loaded 0 table(s)"
    loaded = load_lake_to_bigquery(sources)
    for source, n in loaded.items():
        log.info("bqload    %-22s %12d  -> %s", source, n, table_ref(source))
    total = sum(loaded.values())
    return f"loaded {len(loaded)} table(s), {total:,} rows into BigQuery"
