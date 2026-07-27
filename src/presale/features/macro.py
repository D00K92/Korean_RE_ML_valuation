"""Macro/temporal features: 6-month base-rate delta, months-to-completion.

Macro joins are point-in-time too: join the macro row for the month that was
already published as of the transaction's prediction_date.
"""

from __future__ import annotations

import pandas as pd


def build_macro_features(df: pd.DataFrame, macro_monthly: pd.DataFrame) -> pd.DataFrame:
    """Join macro series and derive rate deltas + months-to-completion.

    TODO: 6-month base-rate delta, months-to-completion; ensure the joined
    macro month is not from the future relative to each row.
    """
    raise NotImplementedError("build_macro_features not yet implemented")
