"""Unit tests for the GCS raw-lake sync (no network / no creds needed).

Exercises the pure layout contract (local path -> object name) and bucket
resolution precedence. The actual upload (gcsfs) is not tested here — it needs a
live bucket; sync_to_gcs imports gcsfs lazily so these run without the dep.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_pipeline.warehouse.gcs import GCSConfigError, local_to_object, resolve_bucket


def test_local_to_object_mirrors_relative_path_under_prefix():
    root = Path("/tmp/data/raw")
    local = root / "molit_resale" / "region=11110" / "data.parquet"
    assert local_to_object(local, root, "raw") == "raw/molit_resale/region=11110/data.parquet"


def test_local_to_object_empty_prefix_has_no_leading_slash():
    root = Path("/tmp/data/raw")
    local = root / "ecos" / "data.parquet"
    assert local_to_object(local, root, "") == "ecos/data.parquet"


def test_resolve_bucket_prefers_env(monkeypatch):
    monkeypatch.setenv("GCS_BUCKET", "env-bucket")
    assert resolve_bucket() == "env-bucket"


def test_resolve_bucket_raises_when_unset(monkeypatch):
    # env empty + settings.yaml gcs.bucket is "" by default -> config error
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with pytest.raises(GCSConfigError):
        resolve_bucket()
