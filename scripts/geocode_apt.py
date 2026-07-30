"""Geocode the apt-trade comp lake (지번 -> lat/lon), one 시군구 at a time.

raw molit_apt_trade -> preprocess (deal_date) -> PARCEL geocode -> processed
comp table with lat/lon + geocode_precision. Per-region writes + a shared
write-through cache make it rollover-safe: distinct parcel addresses are the
only billed calls (~14k total), so a full pass fits one VWorld day.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from presale.config import get_settings
from presale.extract.geocode import GeocodeCache, GeocodeClient
from presale.features.comps import preprocess_raw_apt
from presale.features.geocoding import AddressIndex, geocode_apt


def main() -> None:
    s = get_settings()
    raw_dir = Path(s.get("paths", "raw_dir", default="data/raw")) / "molit_apt_trade"
    out_dir = Path(s.get("paths", "data_root", default="data")) / "processed" / "molit_apt_trade"
    files = sorted(raw_dir.glob("region=*/data.parquet"))
    print(f"apt-trade geocode: {len(files)} 시군구")

    index, client, cache = AddressIndex(), GeocodeClient(), GeocodeCache()
    counts: dict[str, int] = {}
    try:
        for rf in files:
            region = rf.parent.name.split("region=")[1]
            df = pd.read_parquet(rf)
            df["sggCd"] = region  # region lives in the path, not the body
            geo = geocode_apt(preprocess_raw_apt(df), client, cache, index)
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
