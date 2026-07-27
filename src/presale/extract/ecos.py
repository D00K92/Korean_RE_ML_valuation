"""ECOS (Bank of Korea) macro extractor -> monthly macro table.

Series: base rate, mortgage yield, M2 growth, sentiment. Monthly frequency.
Feeds macro features (e.g. 6-month base-rate delta).
"""

from __future__ import annotations

import pandas as pd


def extract() -> pd.DataFrame:
    """Fetch monthly macro series and land a tidy monthly table.

    TODO: ECOS StatisticSearch calls (tenacity retry), tidy to one row per
    year-month, validate against EcosSeriesRecord schema.
    """
    raise NotImplementedError("ECOS extract not yet implemented")


if __name__ == "__main__":
    extract()
