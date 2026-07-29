"""Preprocess the raw apt-trade lake -> cleaned comp table (owner's rules).

Reads every landed raw region file under data/raw/molit_apt_trade/, applies
preprocess_raw_apt (derive deal_date; keep rgstDate; keep cancelled), and writes
one processed file per region under data/processed/apt_comps/region=<code>/.
Idempotent and re-runnable (e.g. after the raw backfill resumes/completes).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from presale.config import get_settings
from presale.features.comps import preprocess_raw_apt

RAW_SUBDIR = "molit_apt_trade"
OUT_SUBDIR = "apt_comps"


def main() -> None:
    settings = get_settings()
    raw_dir = Path(settings.get("paths", "raw_dir", default="data/raw")) / RAW_SUBDIR
    out_dir = Path(settings.get("paths", "data_root", default="data")) / "processed" / OUT_SUBDIR

    region_files = sorted(raw_dir.glob("region=*/data.parquet"))
    if not region_files:
        print(f"no raw apt-trade files under {raw_dir}")
        return

    total = 0
    for rf in region_files:
        region = rf.parent.name.split("region=")[1]
        proc = preprocess_raw_apt(pd.read_parquet(rf))
        dest = out_dir / f"region={region}"
        dest.mkdir(parents=True, exist_ok=True)
        proc.to_parquet(dest / "data.parquet", index=False)
        total += len(proc)
    print(f"preprocessed {len(region_files)} regions, {total} rows -> {out_dir}")


if __name__ == "__main__":
    main()
