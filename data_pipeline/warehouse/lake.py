"""Iterate the Hive-partitioned lake one 시군구 at a time.

Every stage that walks `region=<code>/data.parquet` files — preprocess, geocode —
used to reimplement the same glob/read/write loop. That loop lives here now, so
the runner scripts stay thin and the layout contract (raw vs processed paths,
region-in-path) is defined in exactly one place.

Layout:
    <raw_dir>/<subdir>/region=<code>/data.parquet          # raw lake (base="raw")
    <data_root>/processed/<subdir>/region=<code>/data.parquet   # processed output
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from data_pipeline.config import get_settings


def _raw_root() -> Path:
    return Path(get_settings().get("paths", "raw_dir", default="data/raw"))


def _processed_root() -> Path:
    return Path(get_settings().get("paths", "data_root", default="data")) / "processed"


def region_of(path: Path) -> str:
    """Extract the 시군구 code from a `.../region=<code>/data.parquet` path."""
    return path.parent.name.split("region=")[1]


def iter_region_files(subdir: str, *, base: str = "raw") -> Iterator[tuple[str, Path]]:
    """Yield `(region_code, parquet_path)` for each region file under a lake subdir.

    `base` is "raw" (default) or "processed". Sorted for deterministic order.
    """
    root = _raw_root() if base == "raw" else _processed_root()
    for f in sorted((root / subdir).glob("region=*/data.parquet")):
        yield region_of(f), f


def write_region(
    subdir: str, region: str, df: pd.DataFrame, *, filename: str = "data.parquet"
) -> Path:
    """Write one region's frame under `processed/<subdir>/region=<code>/`."""
    dest = _processed_root() / subdir / f"region={region}"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / filename
    df.to_parquet(path, index=False)
    return path


def dataset_row_counts(local_dir: str | Path | None = None) -> dict[str, int]:
    """Row count per top-level dataset in the raw lake — the ingest sanity check.

    Groups every `*.parquet` under `local_dir` (default: `paths.raw_dir`) by its
    first path component (the source, e.g. `molit_resale`, `commercial`) and sums
    rows. Counts come from each file's Parquet footer (`metadata.num_rows`), so
    this reads no row data and stays cheap even on the full lake. Handles both
    single-file sources (`applyhome/data.parquet`) and region-partitioned ones
    (`molit_resale/region=*/data.parquet`). Returns `{source: rows}` sorted by name.
    """
    root = (
        Path(local_dir)
        if local_dir is not None
        else (Path(get_settings().get("paths", "raw_dir", default="data/raw")))
    )
    counts: dict[str, int] = {}
    for path in sorted(root.glob("**/*.parquet")):
        source = path.relative_to(root).parts[0]
        counts[source] = counts.get(source, 0) + pq.ParquetFile(path).metadata.num_rows
    return dict(sorted(counts.items()))


def map_region_lake(
    raw_subdir: str,
    out_subdir: str,
    transform: Callable[[pd.DataFrame, str], pd.DataFrame],
    *,
    region_col: str | None = None,
    columns: list[str] | None = None,
) -> dict[str, int]:
    """Read each raw region file, apply `transform(df, region)`, write to processed.

    `region_col`, if given, is set on the input frame to the path's region code
    before transform (region lives in the path, not the body). `columns` limits
    the read. Returns a summary dict: regions / rows_in / rows_out.
    """
    summary = {"regions": 0, "rows_in": 0, "rows_out": 0}
    for region, path in iter_region_files(raw_subdir):
        df = pd.read_parquet(path, columns=columns)
        if region_col:
            df[region_col] = region
        out = transform(df, region)
        write_region(out_subdir, region, out)
        summary["regions"] += 1
        summary["rows_in"] += len(df)
        summary["rows_out"] += len(out)
    return summary
