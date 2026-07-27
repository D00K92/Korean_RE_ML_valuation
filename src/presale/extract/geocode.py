"""Geocoding + nearest-station distance (VWorld / Kakao Local).

Geocodes complexes to lat/lon and computes straight-line distance to the
nearest subway station using a static station-coordinate table downloaded once.
"""

from __future__ import annotations

import pandas as pd


def geocode_complexes(df: pd.DataFrame) -> pd.DataFrame:
    """Attach lat/lon to complexes via VWorld or Kakao (whichever key is set).

    TODO: batch geocode with caching so we never re-hit the API for a known
    complex; tenacity retry.
    """
    raise NotImplementedError("geocode_complexes not yet implemented")


def nearest_station_distance(df: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Add straight-line distance (m) to the nearest subway station."""
    raise NotImplementedError("nearest_station_distance not yet implemented")
