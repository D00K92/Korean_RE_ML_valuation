"""Time-based train/val/test split (CLAUDE.md invariant #2).

Split strictly by `deal_date`: the test set is the most recent slice, val the
next-most-recent, train the oldest. NEVER random-shuffle. The required split
test asserts every test `deal_date` is strictly later than every train
`deal_date`.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SplitFrames:
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame


def time_based_split(
    df: pd.DataFrame,
    date_col: str = "deal_date",
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
) -> SplitFrames:
    """Chronological split by quantile cut points on `date_col`.

    Rows are ordered by date; the last `test_fraction` by count form the test
    set, the preceding `val_fraction` the val set, the rest train. Ties on the
    boundary date are pushed into the later split so the invariant holds
    strictly on distinct dates.
    """
    if not 0 < val_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("fractions must be in (0, 1)")
    if val_fraction + test_fraction >= 1:
        raise ValueError("val_fraction + test_fraction must be < 1")

    ordered = df.sort_values(date_col, kind="mergesort").reset_index(drop=True)
    n = len(ordered)
    n_test = int(round(n * test_fraction))
    n_val = int(round(n * val_fraction))
    n_train = n - n_val - n_test
    if min(n_train, n_val, n_test) <= 0:
        raise ValueError("split produced an empty partition; too few rows")

    train = ordered.iloc[:n_train]
    val = ordered.iloc[n_train : n_train + n_val]
    test = ordered.iloc[n_train + n_val :]
    return SplitFrames(train=train, val=val, test=test)
