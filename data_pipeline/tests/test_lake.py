"""Unit tests for storage.lake — the region-file loop shared by the preprocess
and geocode runners. Uses a tmp lake (no real data), monkeypatching the roots."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_pipeline.warehouse import lake


def _seed_raw_lake(root: Path, subdir: str, per_region: dict[str, pd.DataFrame]) -> None:
    for region, df in per_region.items():
        dest = root / subdir / f"region={region}"
        dest.mkdir(parents=True, exist_ok=True)
        df.to_parquet(dest / "data.parquet", index=False)


def test_region_of_parses_hive_partition():
    p = Path("/x/data/raw/molit_resale/region=41192/data.parquet")
    assert lake.region_of(p) == "41192"


def test_iter_region_files_is_sorted(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    monkeypatch.setattr(lake, "_raw_root", lambda: raw)
    _seed_raw_lake(
        raw,
        "src",
        {"41590": pd.DataFrame({"a": [1]}), "11110": pd.DataFrame({"a": [2, 3]})},
    )
    regions = [r for r, _ in lake.iter_region_files("src")]
    assert regions == ["11110", "41590"]  # sorted, deterministic


def test_map_region_lake_applies_transform_and_summarises(tmp_path, monkeypatch):
    raw, proc = tmp_path / "raw", tmp_path / "proc"
    monkeypatch.setattr(lake, "_raw_root", lambda: raw)
    monkeypatch.setattr(lake, "_processed_root", lambda: proc)
    _seed_raw_lake(
        raw,
        "in",
        {"11110": pd.DataFrame({"v": [1, 2, 3]}), "41110": pd.DataFrame({"v": [10, 20]})},
    )

    # transform drops odd values; also assert the region code is passed through
    seen: list[str] = []

    def transform(df: pd.DataFrame, region: str) -> pd.DataFrame:
        seen.append(region)
        return df[df["v"] % 2 == 0]

    summary = lake.map_region_lake("in", "out", transform)

    # 11110: [2] kept (1); 41110: [10,20] kept (2) -> 3 of 5
    assert summary == {"regions": 2, "rows_in": 5, "rows_out": 3}
    assert sorted(seen) == ["11110", "41110"]
    # written per-region under processed/out/region=<code>/
    out_11 = pd.read_parquet(proc / "out" / "region=11110" / "data.parquet")
    assert out_11["v"].tolist() == [2]


def test_dataset_row_counts_sums_per_source(tmp_path, monkeypatch):
    monkeypatch.setattr(lake, "_raw_root", lambda: tmp_path)  # unused, keeps roots isolated
    # region-partitioned source (2 files, 3+2 rows) + a single-file source (1 row)
    _seed_raw_lake(
        tmp_path,
        "molit_resale",
        {"11110": pd.DataFrame({"v": [1, 2, 3]}), "41110": pd.DataFrame({"v": [4, 5]})},
    )
    (tmp_path / "applyhome").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"x": [9]}).to_parquet(tmp_path / "applyhome" / "data.parquet", index=False)

    counts = lake.dataset_row_counts(tmp_path)

    assert counts == {"applyhome": 1, "molit_resale": 5}
    assert list(counts) == ["applyhome", "molit_resale"]  # sorted by source


def test_map_region_lake_sets_region_col_when_asked(tmp_path, monkeypatch):
    raw, proc = tmp_path / "raw", tmp_path / "proc"
    monkeypatch.setattr(lake, "_raw_root", lambda: raw)
    monkeypatch.setattr(lake, "_processed_root", lambda: proc)
    _seed_raw_lake(raw, "in", {"28110": pd.DataFrame({"v": [1]})})

    def transform(df: pd.DataFrame, _region: str) -> pd.DataFrame:
        assert df["region"].tolist() == ["28110"]  # injected from the path
        return df

    lake.map_region_lake("in", "out", transform, region_col="region")
