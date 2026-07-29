"""Preprocess the raw commercial lake -> cleaned amenity table.

Reads every landed raw 시군구 file under data/raw/commercial/, applies
preprocess_raw_commercial (float coords + drop invalid, '' -> null, keep the
useful columns incl. full 업종 hierarchy), and writes one processed file per
시군구 under data/processed/commercial/. Idempotent / re-runnable.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from presale.config import get_settings
from presale.features.comps import preprocess_raw_commercial

RAW_SUBDIR = "commercial"
OUT_SUBDIR = "commercial"


def main() -> None:
    settings = get_settings()
    raw_dir = Path(settings.get("paths", "raw_dir", default="data/raw")) / RAW_SUBDIR
    out_dir = Path(settings.get("paths", "data_root", default="data")) / "processed" / OUT_SUBDIR

    region_files = sorted(raw_dir.glob("region=*/data.parquet"))
    if not region_files:
        print(f"no raw commercial files under {raw_dir}")
        return

    total_in = total_out = 0
    for rf in region_files:
        region = rf.parent.name.split("region=")[1]
        raw = pd.read_parquet(rf)
        proc = preprocess_raw_commercial(raw)
        dest = out_dir / f"region={region}"
        dest.mkdir(parents=True, exist_ok=True)
        proc.to_parquet(dest / "data.parquet", index=False)
        total_in += len(raw)
        total_out += len(proc)
    dropped = total_in - total_out
    print(f"preprocessed {len(region_files)} 시군구: {total_in} -> {total_out} rows "
          f"({dropped} dropped for invalid coords)")


if __name__ == "__main__":
    main()
