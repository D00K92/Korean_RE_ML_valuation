"""Parquet <-> DuckDB helpers.

Raw records land as Hive-partitioned Parquet (partition by deal year-month and
region) and are queried through DuckDB. Keep raw and feature layers separate.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from presale.config import get_settings


def _duckdb_path() -> Path:
    return Path(get_settings().get("paths", "duckdb_path", default="data/presale.duckdb"))


def connect() -> duckdb.DuckDBPyConnection:
    path = _duckdb_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def init_db() -> None:
    """Create the local data lake dirs + DuckDB file. Idempotent (make setup)."""
    settings = get_settings()
    for key in ("data_root", "raw_dir", "feature_dir"):
        Path(settings.get("paths", key, default=f"data/{key}")).mkdir(parents=True, exist_ok=True)
    con = connect()
    con.close()


def write_partitioned(df: pd.DataFrame, subdir: str) -> None:
    """Write a frame as Hive-partitioned Parquet under raw_dir/<subdir>.

    Expects `deal_ym` and `region` columns to partition on.
    """
    settings = get_settings()
    raw_dir = Path(settings.get("paths", "raw_dir", default="data/raw"))
    out = raw_dir / subdir
    out.mkdir(parents=True, exist_ok=True)
    con = connect()
    con.register("_df", df)
    con.execute(
        f"""
        COPY _df TO '{out}'
        (FORMAT PARQUET, PARTITION_BY (region, deal_ym), OVERWRITE_OR_IGNORE)
        """
    )
    con.close()


def read_parquet_glob(pattern: str) -> pd.DataFrame:
    con = connect()
    df = con.execute(f"SELECT * FROM read_parquet('{pattern}', hive_partitioning=1)").df()
    con.close()
    return df
