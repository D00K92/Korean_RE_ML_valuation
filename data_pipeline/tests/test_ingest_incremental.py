"""Tests for MOLIT incremental-ingest logic (no network).

Covers the two quota patches: the fetch manifest (empties recorded + skipped)
and the trailing-refresh window (recent months always re-pulled).
"""

from __future__ import annotations

import pandas as pd
import pytest

import data_pipeline.ingestion.molit as M


def test_shift_ym_handles_year_boundaries():
    assert M._shift_ym("202403", -2) == "202401"
    assert M._shift_ym("202401", -1) == "202312"  # cross year back
    assert M._shift_ym("202312", 1) == "202401"  # cross year forward
    assert M._shift_ym("202607", -6) == "202601"


@pytest.fixture
def temp_lake(tmp_path, monkeypatch):
    """Point the raw dir at a tmp path so manifest/partition writes are isolated."""
    raw = tmp_path / "raw"
    raw.mkdir()
    monkeypatch.setattr(M, "_raw_dir", lambda: raw)
    return raw


def test_manifest_round_trip_records_empties(temp_lake):
    existing = M.load_manifest()
    assert existing.empty  # nothing yet
    pending = [
        {"region": "11110", "deal_ym": "202401", "n_rows": 0, "fetched_at": "t0"},
        {"region": "11110", "deal_ym": "202402", "n_rows": 3, "fetched_at": "t0"},
    ]
    M._write_manifest(existing, pending)

    fetched = M._fetched_set()
    # an empty month is still recorded, so it won't be re-queried next run
    assert ("11110", "202401") in fetched
    assert ("11110", "202402") in fetched
    assert ("11110", "202403") not in fetched


def test_manifest_latest_wins_on_rewrite(temp_lake):
    M._write_manifest(
        pd.DataFrame(columns=["region", "deal_ym", "n_rows", "fetched_at"]),
        [{"region": "41135", "deal_ym": "202405", "n_rows": 0, "fetched_at": "t0"}],
    )
    # a refresh re-pull of the same month updates the row rather than duplicating
    M._write_manifest(
        M.load_manifest(),
        [{"region": "41135", "deal_ym": "202405", "n_rows": 5, "fetched_at": "t1"}],
    )
    man = M.load_manifest()
    row = man[(man["region"] == "41135") & (man["deal_ym"] == "202405")]
    assert len(row) == 1
    assert int(row.iloc[0]["n_rows"]) == 5
    assert row.iloc[0]["fetched_at"] == "t1"
