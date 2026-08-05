"""Preprocess a raw lake into its cleaned table, one 시군구 at a time.

Replaces preprocess_apt.py + preprocess_commercial.py — both were the same
glob/read/write loop over a different transform, now shared via
`storage.lake.map_region_lake`. Idempotent / re-runnable.

Usage:
    uv run python data_pipeline/scripts/preprocess.py --source apt
    uv run python data_pipeline/scripts/preprocess.py --source commercial
"""

from __future__ import annotations

import argparse

from data_pipeline.warehouse.lake import map_region_lake
from ml_pipeline.features.comps import preprocess_raw_apt, preprocess_raw_commercial

# source -> (raw_subdir, out_subdir, transform)
SOURCES = {
    "apt": ("molit_apt_trade", "apt_comps", preprocess_raw_apt),
    "commercial": ("commercial", "commercial", preprocess_raw_commercial),
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    args = ap.parse_args()

    raw_subdir, out_subdir, fn = SOURCES[args.source]
    summary = map_region_lake(raw_subdir, out_subdir, lambda df, _region: fn(df))
    if summary["regions"] == 0:
        print(f"no raw {args.source} files under data/raw/{raw_subdir}")
        return

    dropped = summary["rows_in"] - summary["rows_out"]
    print(
        f"preprocessed {summary['regions']} regions: "
        f"{summary['rows_in']:,} -> {summary['rows_out']:,} rows "
        f"({dropped:,} dropped) -> data/processed/{out_subdir}"
    )


if __name__ == "__main__":
    main()
