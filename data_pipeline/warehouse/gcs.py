"""Mirror the local Parquet lake to a GCS bucket.

The Airflow pipeline stages raw records as Hive-partitioned Parquet in the local
`data/` lake (see parquet_io.py), then syncs that tree to a GCS bucket.
Extractors in `data_pipeline/ingestion/*` stay GCS-agnostic — they only ever
write local parquet; this module owns the upload, and the DAG calls it as one
thin task (then bigquery_io.py loads GCS -> the BigQuery contract tables).

Credentials are resolved by google-auth from `GOOGLE_APPLICATION_CREDENTIALS`
(a service-account key *path*) or an Airflow `google_cloud_default` connection —
never a key value in code. The bucket name is a non-secret tunable
(config.yaml `gcs.bucket`, overridable by the `GCS_BUCKET` env var).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from data_pipeline.config import PROJECT_ROOT, get_settings

logger = logging.getLogger(__name__)


class GCSConfigError(RuntimeError):
    """Raised when a GCS sync is requested but no bucket is configured."""


def resolve_bucket() -> str:
    """Bucket name: `GCS_BUCKET` env wins, else config.yaml `gcs.bucket`.

    A bucket name is not a secret, so it is safe to surface in errors/logs.
    """
    env = os.environ.get("GCS_BUCKET", "").strip()
    if env:
        return env
    cfg = str(get_settings().get("gcs", "bucket", default="") or "").strip()
    if cfg:
        return cfg
    raise GCSConfigError(
        "No GCS bucket configured. Set GCS_BUCKET in the environment or gcs.bucket in config.yaml."
    )


def local_to_object(local_path: Path, local_root: Path, prefix: str) -> str:
    """Map a local file path to its `<prefix>/<relative-path>` object name.

    Pure function (no I/O) so the layout contract is unit-testable. Always emits
    POSIX-style separators, since GCS object names use '/'.
    """
    rel = local_path.relative_to(local_root).as_posix()
    prefix = prefix.strip("/")
    return f"{prefix}/{rel}" if prefix else rel


def sync_to_gcs(
    local_dir: str | os.PathLike[str] | None = None,
    *,
    bucket: str | None = None,
    prefix: str | None = None,
    pattern: str = "**/*.parquet",
) -> list[str]:
    """Upload every file matching `pattern` under `local_dir` to `gs://bucket/prefix`.

    Args:
        local_dir: local tree to mirror. Defaults to the raw lake
            (`paths.raw_dir`, e.g. ``data/raw``).
        bucket: target bucket. Defaults to :func:`resolve_bucket`.
        prefix: object-name prefix. Defaults to `gcs.raw_prefix` (e.g. ``raw``).
        pattern: glob of files to sync (default: all parquet).

    Returns the list of `gs://` URIs written. Import-light: `gcsfs` is imported
    lazily so unit tests can exercise :func:`local_to_object` without the dep.
    """
    import gcsfs  # lazy — keeps the module importable without GCS deps installed

    settings = get_settings()
    root = (
        Path(local_dir)
        if local_dir is not None
        else (PROJECT_ROOT / settings.get("paths", "raw_dir", default="data/raw"))
    )
    if not root.exists():
        raise FileNotFoundError(f"local_dir does not exist: {root}")

    bucket = bucket or resolve_bucket()
    prefix = prefix if prefix is not None else str(settings.get("gcs", "raw_prefix", default="raw"))
    project = settings.get("gcp", "project", default=None) or None

    # google-auth picks up GOOGLE_APPLICATION_CREDENTIALS / ADC automatically.
    fs = gcsfs.GCSFileSystem(project=project)

    files = sorted(p for p in root.glob(pattern) if p.is_file())
    written: list[str] = []
    for local_path in files:
        obj = local_to_object(local_path, root, prefix)
        dst = f"{bucket}/{obj}"
        fs.put_file(str(local_path), dst)
        written.append(f"gs://{dst}")

    logger.info("Synced %d file(s) from %s to gs://%s/%s", len(written), root, bucket, prefix)
    return written
