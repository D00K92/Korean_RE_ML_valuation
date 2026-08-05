"""BigQuery read/write for the ML pillar.

The ML pipeline reads its inputs from the ``korea_real_estate.*`` contract tables
the data pillar produced, and writes the assembled feature matrix back as the
``features`` table. It authenticates with Application Default Credentials
(``google.auth.default()`` / ``GOOGLE_APPLICATION_CREDENTIALS``) and never imports
``data_pipeline`` — BigQuery *is* the boundary between the two pillars.
"""

from __future__ import annotations

import logging

import pandas as pd

from ml_pipeline.config import get_settings

logger = logging.getLogger(__name__)


def _client():
    from google.cloud import bigquery

    return bigquery.Client(project=get_settings().get("gcp", "project", default=None) or None)


def read_table(name: str, *, columns: list[str] | None = None) -> pd.DataFrame:
    """Read a contract table (logical name, e.g. ``molit_resale``) into a DataFrame.

    Uses an explicit column list when given (avoid ``SELECT *`` in production);
    otherwise selects all columns of the resolved ``project.dataset.table``.
    """
    table = get_settings().bq_table(name)
    select = ", ".join(f"`{c}`" for c in columns) if columns else "*"
    return read_query(f"SELECT {select} FROM `{table}`")


def read_query(sql: str) -> pd.DataFrame:
    """Run a SQL query and return the result as a DataFrame (BQ Storage API if available)."""
    logger.info("bq query: %s", sql.replace("\n", " ")[:200])
    return _client().query(sql).to_dataframe()


def write_table(df: pd.DataFrame, name: str, *, write_disposition: str = "WRITE_TRUNCATE") -> str:
    """Write a DataFrame to a contract table (logical name). Returns the table ref."""
    from google.cloud import bigquery

    table = get_settings().bq_table(name)
    job_config = bigquery.LoadJobConfig(write_disposition=write_disposition)
    _client().load_table_from_dataframe(df, table, job_config=job_config).result()
    logger.info("wrote %d rows -> %s", len(df), table)
    return table
