"""Preprocessing for the raw 아파트 매매 comp source (data/raw/molit_apt_trade).

Raw apt-trade is landed untransformed (see extract/molit_apt.py). This module
turns it into the cleaned comp table used for spatial comparable-sales features.
Transforms are applied here (not at ingest) so raw stays auditable and rules can
change without re-fetching ~1M rows.

Preprocessing rules (owner-directed, 2026-07-28):
  - combine dealYear/Month/Day -> deal_date
  - keep rgstDate (등기일자) as-is
  - keep cancelled (cdealType) rows — a later-cancelled sale still reflects the
    market price at the time, which is what a comp needs
"""

from __future__ import annotations

import pandas as pd

# commercial (상가) fields we keep for amenity features — the full 업종 hierarchy
# (so we can filter to groceries/malls/etc. at feature time) + id/name/location.
_COMMERCIAL_KEEP = [
    "bizesId", "bizesNm", "brchNm",
    "indsLclsCd", "indsLclsNm", "indsMclsCd", "indsMclsNm", "indsSclsCd", "indsSclsNm",
    "ksicCd", "ksicNm",
    "signguCd", "ldongCd", "adongCd",
    "lnoAdr", "rdnmAdr",
    "lon", "lat", "region",
]


def preprocess_raw_apt(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the agreed apt-trade preprocessing. Returns a new frame.

    Currently: derive `deal_date` from the split y/m/d columns; everything else
    (rgstDate, cdealType, dealAmount, excluUseAr, ...) is preserved as-is.
    """
    if df.empty:
        return df
    out = df.copy()
    out["deal_date"] = pd.to_datetime(
        {
            "year": out["dealYear"].astype(int),
            "month": out["dealMonth"].astype(int),
            "day": out["dealDay"].astype(int),
        },
        errors="coerce",
    )
    return out


def preprocess_raw_commercial(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the raw 상가(상권) POIs into an amenity table.

    Rules: cast lat/lon to float and drop rows without valid Korea coords (a POI
    with no location is useless); normalize '' -> null; keep the ~19 useful
    columns incl. the full 업종 hierarchy (업종 filtering stays at feature time).
    """
    if df.empty:
        return df
    out = df.copy()
    for col in ("lat", "lon"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    # valid Korea bounding box; drops null/zero/garbage coords
    out = out[out["lat"].between(33, 39) & out["lon"].between(124, 132)]
    out = out.replace("", pd.NA)
    keep = [c for c in _COMMERCIAL_KEEP if c in out.columns]
    return out[keep].reset_index(drop=True)
