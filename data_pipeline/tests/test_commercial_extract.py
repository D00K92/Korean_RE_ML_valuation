"""Unit tests for commercial.extract mode gating (backfill vs refresh).

No network/IO: fetch, manifest, and parquet-write are stubbed so we only assert
*which* 시군구 get fetched. Region 11110 starts "already manifested"."""

from __future__ import annotations

import pandas as pd
import pytest

from data_pipeline.ingestion import commercial


@pytest.fixture
def fetch_calls(monkeypatch):
    calls: list[str] = []

    # 11110 already landed; 41110 is new
    monkeypatch.setattr(
        commercial,
        "load_manifest",
        lambda: pd.DataFrame({"region": ["11110"], "n_rows": [5], "fetched_at": ["x"]}),
    )
    monkeypatch.setattr(commercial, "_write_manifest", lambda existing, pending: existing)
    monkeypatch.setattr(commercial, "write_region_parquet", lambda df, sub, region: None)
    monkeypatch.setattr(commercial.time, "sleep", lambda *_: None)

    def fake_fetch(region: str) -> pd.DataFrame:
        calls.append(region)
        return pd.DataFrame({"a": ["1"], "region": [region]})

    monkeypatch.setattr(commercial, "fetch_sigungu", fake_fetch)
    return calls


def test_backfill_skips_manifested_region(fetch_calls):
    commercial.extract(regions=["11110", "41110"], mode="backfill")
    assert fetch_calls == ["41110"]  # 11110 skipped — already in manifest


def test_refresh_refetches_every_region(fetch_calls):
    commercial.extract(regions=["11110", "41110"], mode="refresh")
    assert fetch_calls == ["11110", "41110"]  # both re-pulled
