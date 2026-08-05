"""Geocode a raw lake to lat/lon with the cascade appropriate to the target.

Replaces geocode_apt.py + geocode_label.py + geocode_schools.py. The per-region
loop (read region file -> geocode -> write processed -> tally precision) that apt
and label used to each reimplement lives once in `_geocode_per_region`. Cache-
backed + write-through, so a VWorld/Kakao quota stop resumes losslessly on rerun.

Targets:
    apt      apt-trade comps  : PARCEL cascade (지번 -> lat/lon)         [run first]
    label    분양권 label      : 4-tier cascade (borrows apt coords; needs apt done)
    schools  NEIS schools     : ROAD cascade (single file, not region-partitioned)

Usage:
    uv run python data_pipeline/scripts/geocode.py --target apt
    uv run python data_pipeline/scripts/geocode.py --target label
    uv run python data_pipeline/scripts/geocode.py --target schools
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from data_pipeline.config import get_settings
from data_pipeline.ingestion import geocoding as G
from data_pipeline.ingestion.geocode import GeocodeCache, GeocodeClient
from data_pipeline.warehouse.lake import iter_region_files, write_region
from ml_pipeline.features.comps import preprocess_raw_apt

# per-region geocode signature: (df, region, client, cache, index) -> geocoded df
PerRegion = Callable[[pd.DataFrame, str, GeocodeClient, GeocodeCache, G.AddressIndex], pd.DataFrame]


def _geocode_per_region(raw_subdir: str, out_subdir: str, per_region: PerRegion) -> None:
    files = list(iter_region_files(raw_subdir))
    print(f"{out_subdir} geocode: {len(files)} 시군구")
    client, cache, index = GeocodeClient(), GeocodeCache(), G.AddressIndex()
    counts: dict[str, int] = {}
    try:
        for region, path in files:
            geo = per_region(pd.read_parquet(path), region, client, cache, index)
            write_region(out_subdir, region, geo)
            for k, v in geo["geocode_precision"].value_counts().items():
                counts[k] = counts.get(k, 0) + int(v)
            print(f"  {region}: {len(geo):,} rows  cache={len(cache):,}")
    finally:
        cache.flush()
        client.close()
    print("\nprecision totals:", counts)


def _load_borrow_index() -> dict:
    """(base_name, sgg) -> Coord index built from the already-geocoded apt lake."""
    frames = []
    for region, path in iter_region_files("molit_apt_trade", base="processed"):
        d = pd.read_parquet(path, columns=["aptNm", "lat", "lon"])
        d["sggCd"] = region
        frames.append(d)
    if not frames:
        print(
            "WARNING: no geocoded apt-trade found — borrow tier disabled "
            "(run --target apt first for best coverage)"
        )
        return {}
    idx = G.build_borrow_index(pd.concat(frames, ignore_index=True))
    print(f"borrow index: {len(idx):,} complexes from {len(frames)} geocoded apt 시군구")
    return idx


def _do_apt() -> None:
    def per(df, region, client, cache, index):
        df["sggCd"] = region  # region lives in the path, not the body
        return G.geocode_apt(preprocess_raw_apt(df), client, cache, index)

    _geocode_per_region("molit_apt_trade", "molit_apt_trade", per)


def _do_label() -> None:
    borrow = _load_borrow_index()

    def per(df, region, client, cache, index):
        df["region_code"] = region
        return G.geocode_label(df, client, cache, borrow_index=borrow, index=index)

    _geocode_per_region("molit_resale", "molit_resale", per)


def _do_schools() -> None:
    s = get_settings()
    raw = Path(s.get("paths", "raw_dir", default="data/raw")) / "schools" / "data.parquet"
    df = pd.read_parquet(raw)
    print(f"schools: {len(df):,} rows -> geocoding (ROAD, keyword fallback)")

    client, cache = GeocodeClient(), GeocodeCache()
    try:
        geo = G.geocode_schools(df, client, cache)
    finally:
        cache.flush()
        client.close()

    out = Path(s.get("paths", "data_root", default="data")) / "processed" / "schools"
    out.mkdir(parents=True, exist_ok=True)
    geo.to_parquet(out / "geocoded.parquet", index=False)
    ok = geo["lat"].notna().mean() * 100
    print(f"\nresolved {geo['lat'].notna().sum():,}/{len(geo):,} ({ok:.1f}%)")
    print(geo["geocode_precision"].value_counts().to_string())


TARGETS = {"apt": _do_apt, "label": _do_label, "schools": _do_schools}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    args = ap.parse_args()
    TARGETS[args.target]()


if __name__ == "__main__":
    main()
