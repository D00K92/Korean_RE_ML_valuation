"""Required invariant test (CLAUDE.md #1): no look-ahead in features.

Asserts no comp with report_date (= deal_date + reporting_lag) after the row's
prediction_date can enter a feature row.
"""

from __future__ import annotations

import pandas as pd

from ml_pipeline.features.spatial import report_date, usable_comps

REPORTING_LAG_DAYS = 30


def _comps() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "deal_date": pd.to_datetime(["2024-01-01", "2024-02-15", "2024-03-01", "2024-03-20"]),
            "price_per_m2": [1000, 1100, 1200, 1300],
        }
    )


def test_usable_comps_excludes_future_reports():
    prediction_date = pd.Timestamp("2024-03-15")
    kept = usable_comps(_comps(), prediction_date, REPORTING_LAG_DAYS)
    reported = report_date(kept["deal_date"], REPORTING_LAG_DAYS)
    # every kept comp must have been reported on/before the prediction date
    assert (reported <= prediction_date).all()


def test_comp_at_lag_boundary_is_included():
    # deal on 2024-02-15 reports on 2024-03-16; prediction exactly then -> usable
    prediction_date = pd.Timestamp("2024-03-16")
    kept = usable_comps(_comps(), prediction_date, REPORTING_LAG_DAYS)
    assert pd.Timestamp("2024-02-15") in set(kept["deal_date"])


def test_comp_one_day_short_of_lag_is_excluded():
    prediction_date = pd.Timestamp("2024-03-15")  # 2024-02-15 reports 03-16
    kept = usable_comps(_comps(), prediction_date, REPORTING_LAG_DAYS)
    assert pd.Timestamp("2024-02-15") not in set(kept["deal_date"])


def test_empty_comps_returns_empty():
    empty = pd.DataFrame({"deal_date": pd.to_datetime([])})
    assert usable_comps(empty, pd.Timestamp("2024-01-01"), REPORTING_LAG_DAYS).empty
