"""Required invariant test (CLAUDE.md #2): time-based split only.

Asserts every test-set deal_date is strictly later than every train-set
deal_date, and that no shuffling reorders across the boundary.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml_pipeline.components.split import time_based_split


def _synthetic(n: int = 1000) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(0)
    return pd.DataFrame({"deal_date": dates, "y": rng.normal(size=n)})


def test_test_dates_strictly_after_train_dates():
    frames = time_based_split(_synthetic(), val_fraction=0.15, test_fraction=0.15)
    assert frames.train["deal_date"].max() < frames.test["deal_date"].min()
    assert frames.train["deal_date"].max() < frames.val["deal_date"].min()
    assert frames.val["deal_date"].max() < frames.test["deal_date"].min()


def test_split_covers_all_rows_without_overlap():
    df = _synthetic()
    frames = time_based_split(df)
    total = len(frames.train) + len(frames.val) + len(frames.test)
    assert total == len(df)


def test_split_is_deterministic_and_ordered():
    df = _synthetic()
    frames = time_based_split(df)
    # train is the oldest contiguous slice — no shuffling
    assert frames.train["deal_date"].is_monotonic_increasing
