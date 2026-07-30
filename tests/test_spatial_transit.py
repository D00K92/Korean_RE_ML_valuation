"""Tests for transit (metro/bus) proximity features — known-distance geometry."""

from __future__ import annotations

import numpy as np
import pandas as pd

from presale.features.spatial import add_transit_features

# 1 degree of latitude ~= 111.19 km; use it to place stations at known distances.
_M_PER_DEG_LAT = np.pi / 180 * 6_371_000.0


def _stations():
    # station A at (37.5, 127.0); station B ~900 m north on line 2
    return pd.DataFrame(
        {
            "station_name": ["A", "B"],
            "line": ["1호선", "2호선"],
            "lat": [37.5, 37.5 + 900 / _M_PER_DEG_LAT],
            "lon": [127.0, 127.0],
        }
    )


def _props():
    # P1 sits exactly on station A; P2 is ~300 m north of A
    return pd.DataFrame(
        {
            "lat": [37.5, 37.5 + 300 / _M_PER_DEG_LAT],
            "lon": [127.0, 127.0],
        }
    )


def test_nearest_metro_distance_and_line():
    out = add_transit_features(_props(), subway=_stations(), metro_radii_m=(500,))
    # P1 on top of A -> ~0 m, nearest line = A's line
    assert out.loc[0, "nearest_metro_dist_m"] < 1.0
    assert out.loc[0, "nearest_metro_line"] == "1호선"
    # P2 ~300 m from A
    assert abs(out.loc[1, "nearest_metro_dist_m"] - 300) < 5


def test_within_radius_counts():
    out = add_transit_features(_props(), subway=_stations(), metro_radii_m=(500, 1000))
    # P1: A within 500m (B is ~900m, outside 500) -> 1; both within 1000m -> 2
    assert out.loc[0, "n_metro_within_500m"] == 1
    assert out.loc[0, "n_metro_within_1000m"] == 2


def test_bus_features_and_null_safe_coords():
    props = pd.DataFrame({"lat": [37.5, np.nan], "lon": [127.0, np.nan]})
    bus = pd.DataFrame({"stop_name": ["b1"], "lat": [37.5], "lon": [127.0]})
    out = add_transit_features(props, bus=bus, bus_radii_m=(300,))
    assert out.loc[0, "nearest_bus_dist_m"] < 1.0
    assert out.loc[0, "n_bus_stops_within_300m"] == 1
    # row without coords -> NaN, never crashes
    assert pd.isna(out.loc[1, "nearest_bus_dist_m"])
