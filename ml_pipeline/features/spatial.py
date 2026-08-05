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

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

_EARTH_M = 6_371_000.0  # mean earth radius, metres (haversine * this = metres)


# ---------------------------------------------------------------------------
# Transit proximity (metro / bus) — static amenity features
#
# Nearest-neighbour distance + within-radius counts from the geocoded property
# to the GCS-backed reference station/stop tables (gs://<bucket>/reference/
# {subway_stations,bus_stops}.parquet). Straight-line haversine via a BallTree. No point-in-time
# filter is applied: the station files carry no open-date, so a pre-opening deal
# could "see" a later-opened line (e.g. GTX / 김포골드) — a known limitation, small
# for our window, noted in the README rather than silently corrected.
# ---------------------------------------------------------------------------
def _haversine_tree(ref: pd.DataFrame) -> BallTree:
    return BallTree(np.radians(ref[["lat", "lon"]].to_numpy(float)), metric="haversine")


def _nearest_and_counts(
    props: pd.DataFrame, ref: pd.DataFrame, radii_m: tuple[int, ...]
) -> tuple[np.ndarray, np.ndarray, dict[int, np.ndarray]]:
    """Nearest distance (m) + nearest index + per-radius counts, props -> ref."""
    tree = _haversine_tree(ref)
    pc = np.radians(props[["lat", "lon"]].to_numpy(float))
    dist, idx = tree.query(pc, k=1)
    nearest_m = dist[:, 0] * _EARTH_M
    counts = {r: tree.query_radius(pc, r=r / _EARTH_M, count_only=True) for r in radii_m}
    return nearest_m, idx[:, 0], counts


def add_transit_features(
    props: pd.DataFrame,
    subway: pd.DataFrame | None = None,
    bus: pd.DataFrame | None = None,
    metro_radii_m: tuple[int, ...] = (500, 1000),
    bus_radii_m: tuple[int, ...] = (300,),
) -> pd.DataFrame:
    """Add nearest-metro/bus distance + density features to geocoded `props`.

    `props` needs lat/lon; rows missing coords get NaN. Adds:
      nearest_metro_dist_m, nearest_metro_line, n_metro_within_<r>m
      nearest_bus_dist_m,   n_bus_stops_within_<r>m
    """
    out = props.copy()
    has = out["lat"].notna() & out["lon"].notna()
    sub = out.loc[has]

    if subway is not None and not sub.empty:
        nm, ni, ct = _nearest_and_counts(sub, subway, metro_radii_m)
        out.loc[has, "nearest_metro_dist_m"] = nm
        out.loc[has, "nearest_metro_line"] = subway["line"].to_numpy()[ni]
        for r in metro_radii_m:
            out.loc[has, f"n_metro_within_{r}m"] = ct[r]

    if bus is not None and not sub.empty:
        nm, _ni, ct = _nearest_and_counts(sub, bus, bus_radii_m)
        out.loc[has, "nearest_bus_dist_m"] = nm
        for r in bus_radii_m:
            out.loc[has, f"n_bus_stops_within_{r}m"] = ct[r]

    return out


# ---------------------------------------------------------------------------
# School quality (학군) — selective-HS proximity + area 진학률
#
# 학교알리미 (apiType 51) gives HS type (특목고/자율고) + 진학률 keyed by name, but no
# coords. We attach coords by joining SCHUL_NM to the already-geocoded NEIS schools,
# then measure proximity to *selective* high schools. Near-static snapshot (API =
# last 3 yrs only) → NOT point-in-time for pre-2023 rows; a documented limitation.
# ---------------------------------------------------------------------------
def _norm_name(s: object) -> str:
    return "".join(str(s).split())


def build_selective_schools(
    schoolinfo: pd.DataFrame,
    geocoded_schools: pd.DataFrame,
    selective_types: tuple[str, ...] = ("특수목적고등학교", "자율고등학교"),
) -> pd.DataFrame:
    """Selective HS (특목고/자율고) with lat/lon, from schoolinfo ⨝ geocoded NEIS by name."""
    coords = geocoded_schools.dropna(subset=["lat", "lon"]).copy()
    coords["_k"] = coords["name"].map(_norm_name)
    coord_map = coords.drop_duplicates("_k").set_index("_k")[["lat", "lon"]]
    sel = schoolinfo[schoolinfo["hs_type"].isin(selective_types)].copy()
    sel["_k"] = sel["name"].map(_norm_name)
    sel = sel.join(coord_map, on="_k").dropna(subset=["lat", "lon"])
    return sel[["name", "hs_type", "grad_rate", "lat", "lon"]].reset_index(drop=True)


def add_school_quality_features(
    props: pd.DataFrame,
    selective_schools: pd.DataFrame,
    radii_m: tuple[int, ...] = (2000,),
) -> pd.DataFrame:
    """Add nearest-selective-HS distance + within-radius count to geocoded `props`."""
    out = props.copy()
    has = out["lat"].notna() & out["lon"].notna()
    if selective_schools.empty or not has.any():
        return out
    nm, _ni, ct = _nearest_and_counts(out.loc[has], selective_schools, radii_m)
    out.loc[has, "nearest_selective_hs_dist_m"] = nm
    for r in radii_m:
        out.loc[has, f"n_selective_hs_within_{r}m"] = ct[r]
    return out


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
