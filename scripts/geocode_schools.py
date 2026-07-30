"""Geocode NEIS schools (ROAD 도로명주소 -> lat/lon) — the end-to-end geocoder proof.

Reads the raw schools lake, runs the ROAD cascade (keyword fallback), writes
data/processed/schools/geocoded.parquet, and prints a precision breakdown.
Cache-backed + write-through, so a quota stop resumes losslessly on rerun.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from presale.config import get_settings
from presale.extract.geocode import GeocodeCache, GeocodeClient
from presale.features.geocoding import geocode_schools


def main() -> None:
    s = get_settings()
    raw = Path(s.get("paths", "raw_dir", default="data/raw")) / "schools" / "data.parquet"
    out = Path(s.get("paths", "data_root", default="data")) / "processed" / "schools"
    df = pd.read_parquet(raw)
    print(f"schools: {len(df):,} rows -> geocoding (ROAD, keyword fallback)")

    client, cache = GeocodeClient(), GeocodeCache()
    try:
        geo = geocode_schools(df, client, cache)
    finally:
        cache.flush()
        client.close()

    out.mkdir(parents=True, exist_ok=True)
    geo.to_parquet(out / "geocoded.parquet", index=False)
    ok = geo["lat"].notna().mean() * 100
    print(f"\nresolved {geo['lat'].notna().sum():,}/{len(geo):,} ({ok:.1f}%)")
    print(geo["geocode_precision"].value_counts().to_string())


if __name__ == "__main__":
    main()
