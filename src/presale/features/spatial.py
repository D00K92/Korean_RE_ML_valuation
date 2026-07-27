"""Spatial comp features with strict point-in-time correctness.

The single highest-signal thing in the project (CLAUDE.md invariant #1): a comp
transaction is usable for a row only if it was publicly *reported* as of the
row's prediction_date, i.e.

    comp.deal_date + reporting_lag <= row.prediction_date

`usable_comps` is the leakage guard the required test asserts against. When in
doubt, exclude.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd


def report_date(deal_date: pd.Series, reporting_lag_days: int) -> pd.Series:
    """The date a deal became publicly usable = deal_date + reporting lag."""
    return pd.to_datetime(deal_date) + pd.to_timedelta(reporting_lag_days, unit="D")


def usable_comps(
    comps: pd.DataFrame,
    prediction_date: dt.date | pd.Timestamp,
    reporting_lag_days: int,
) -> pd.DataFrame:
    """Return only comps reported on/before `prediction_date`.

    `comps` must have a `deal_date` column. No look-ahead: a comp whose
    reporting date is after prediction_date is dropped, never joined.
    """
    if comps.empty:
        return comps
    rep = report_date(comps["deal_date"], reporting_lag_days)
    mask = rep <= pd.Timestamp(prediction_date)
    return comps.loc[mask].copy()


def weighted_comp_price_per_m2(
    row: pd.Series,
    comps: pd.DataFrame,
    reporting_lag_days: int,
    radius_m: float,
    window_days: int,
) -> float:
    """Distance-weighted mean comp price/㎡ within radius+window, point-in-time.

    TODO: haversine/straight-line distance filter + trailing window + inverse-
    distance weighting. Must call `usable_comps` first — never bypass the lag.
    """
    raise NotImplementedError("weighted_comp_price_per_m2 not yet implemented")


def build_spatial_features(rows: pd.DataFrame, comps: pd.DataFrame) -> pd.DataFrame:
    """Comp features at all configured radii × windows, with dynamic expansion.

    TODO: iterate config radii/windows; dynamic radius expansion for sparse
    areas (500m -> 1km -> 3km -> district) until min_comps is met.
    """
    raise NotImplementedError("build_spatial_features not yet implemented")
