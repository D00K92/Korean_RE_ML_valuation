"""Property features: area, floor, building age, 전용률, log(units), brand tier."""

from __future__ import annotations

import pandas as pd


def build_property_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive per-transaction property features.

    TODO: exclusive area, floor, building age, 전용률 (usable-space ratio),
    log(total units), developer tier (Top-10 brand vs regional).
    """
    raise NotImplementedError("build_property_features not yet implemented")
