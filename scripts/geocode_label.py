"""Geocode the 분양권 label lake with the four-tier cascade, one 시군구 at a time.

raw molit_resale -> [PARCEL | apt-coord borrow | keyword | dong-centroid] ->
processed label table with lat/lon + geocode_precision. The borrow tier reuses
the already-geocoded apt-trade lake (run scripts/geocode_apt.py first) to place
block-code rows for free; anything left resolves by Kakao keyword, else a
flagged dong-centroid so no row is ever dropped.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from presale.config import get_settings
from presale.extract.geocode import GeocodeCache, GeocodeClient
from presale.features.geocoding import AddressIndex, build_borrow_index, geocode_label


def _load_borrow_index() -> dict:
    """Build the (base_name, sgg) -> Coord borrow index from geocoded apt-trade."""
    s = get_settings()
    apt_dir = Path(s.get("paths", "data_root", default="data")) / "processed" / "molit_apt_trade"
    files = sorted(apt_dir.glob("region=*/data.parquet"))
    if not files:
        print("WARNING: no geocoded apt-trade found — borrow tier disabled "
              "(run scripts/geocode_apt.py first for best coverage)")
        return {}
    frames = []
    for f in files:
        region = f.parent.name.split("region=")[1]
        d = pd.read_parquet(f, columns=["aptNm", "lat", "lon"])
        d["sggCd"] = region
        frames.append(d)
    apt = pd.concat(frames, ignore_index=True)
    idx = build_borrow_index(apt)
    print(f"borrow index: {len(idx):,} complexes from {len(files)} geocoded apt 시군구")
    return idx


def main() -> None:
    s = get_settings()
    raw_dir = Path(s.get("paths", "raw_dir", default="data/raw")) / "molit_resale"
    out_dir = Path(s.get("paths", "data_root", default="data")) / "processed" / "molit_resale"
    files = sorted(raw_dir.glob("region=*/data.parquet"))
    print(f"label geocode: {len(files)} 시군구")

    borrow = _load_borrow_index()
    index, client, cache = AddressIndex(), GeocodeClient(), GeocodeCache()
    counts: dict[str, int] = {}
    try:
        for rf in files:
            region = rf.parent.name.split("region=")[1]
            df = pd.read_parquet(rf)
            df["region_code"] = region  # region lives in the path, not the body
            geo = geocode_label(df, client, cache, borrow_index=borrow, index=index)
            dest = out_dir / f"region={region}"
            dest.mkdir(parents=True, exist_ok=True)
            geo.to_parquet(dest / "data.parquet", index=False)
            for k, v in geo["geocode_precision"].value_counts().items():
                counts[k] = counts.get(k, 0) + int(v)
            print(f"  {region}: {len(geo):,} rows  cache={len(cache):,}")
    finally:
        cache.flush()
        client.close()
    print("\nprecision totals:", counts)


if __name__ == "__main__":
    main()
