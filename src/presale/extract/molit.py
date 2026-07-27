"""MOLIT 분양권전매 실거래가 extractor — the training label source.

Responsibilities (Day 1–2):
  - paginate the data.go.kr endpoint per (LAWD_CD, deal year-month)
  - auto-detect encoding (EUC-KR vs UTF-8) with chardet before XML parse
  - retry with backoff (tenacity), respect rate limits
  - validate each record against the pydantic schema
  - land Hive-partitioned Parquet (partition by deal year-month + region)

This module is import-only business logic; the CLI at the bottom exists so the
Makefile / Airflow can invoke it, but the real entry point is `extract()`.
"""

from __future__ import annotations

import argparse
from typing import Literal

import pandas as pd

from presale.config import get_settings


def fetch_month(lawd_cd: str, deal_ym: str) -> pd.DataFrame:
    """Fetch one (region, year-month) page set. Returns validated rows.

    TODO: httpx call + chardet encoding detect + xmltodict parse + tenacity
    retry + MolitResaleRecord schema validation.
    """
    raise NotImplementedError("MOLIT fetch_month not yet implemented")


def extract(mode: Literal["latest", "backfill"] = "latest") -> pd.DataFrame:
    """Extract resale transactions for the configured region.

    `latest` pulls the most recent month; `backfill` walks start_ym -> present.
    Lands raw Parquet and returns the combined frame.
    """
    settings = get_settings()
    lawd_codes: list[str] = settings.get("region", "lawd_codes", default=[])
    if not lawd_codes:
        raise RuntimeError(
            "No region lawd_codes configured. Set them in config/settings.yaml "
            "after validating region volume (Day 1)."
        )
    raise NotImplementedError("MOLIT extract not yet implemented")


def main() -> None:
    parser = argparse.ArgumentParser(description="MOLIT resale extractor")
    parser.add_argument("--mode", choices=["latest", "backfill"], default="latest")
    args = parser.parse_args()
    extract(mode=args.mode)


if __name__ == "__main__":
    main()
