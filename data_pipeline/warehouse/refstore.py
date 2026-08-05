"""Resolve static reference files to a local path — GCS-backed, locally cached.

The 법정동 code tables and transit station/stop coordinates are static lookup
*inputs* to ingestion/features. Their source of truth is
``gs://<bucket>/<reference_prefix>/<name>``; they are fetched once into a
gitignored local cache (``.cache/reference/``) and reused. There is no local
``data/`` lake — everything is queried from the cloud.

Set the ``REFERENCE_DIR`` env var to a local directory to bypass GCS entirely
(tests point it at ``data_pipeline/tests/fixtures/reference`` so the suite runs fully offline).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from data_pipeline.config import PROJECT_ROOT, get_settings

logger = logging.getLogger(__name__)

DEFAULT_REFERENCE_PREFIX = "reference"


def cache_dir() -> Path:
    return PROJECT_ROOT / ".cache" / "reference"


def reference_path(name: str) -> Path:
    """Local path to reference file ``name``, fetching it from GCS if needed.

    ``REFERENCE_DIR`` (if set) wins and is used directly — no GCS, no cache. This
    is the offline/test path. Otherwise the file is downloaded once from
    ``gs://<bucket>/<reference_prefix>/<name>`` into the local cache.
    """
    override = os.environ.get("REFERENCE_DIR", "").strip()
    if override:
        return Path(override) / name
    cached = cache_dir() / name
    if not cached.exists():
        _download(name, cached)
    return cached


def _download(name: str, dest: Path) -> None:
    import gcsfs

    from data_pipeline.warehouse.gcs import resolve_bucket

    settings = get_settings()
    bucket = resolve_bucket()
    prefix = str(settings.get("gcs", "reference_prefix", default=DEFAULT_REFERENCE_PREFIX)).strip(
        "/"
    )
    src = f"{bucket}/{prefix}/{name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fs = gcsfs.GCSFileSystem(project=settings.get("gcp", "project", default=None) or None)
    fs.get_file(src, str(dest))
    logger.info("cached reference gs://%s -> %s", src, dest)


def upload_reference(local_dir: str | os.PathLike[str], names: list[str]) -> list[str]:
    """Upload local reference files to ``gs://<bucket>/<reference_prefix>/``.

    One-shot helper to seed the cloud reference store. Returns the gs:// URIs.
    """
    import gcsfs

    from data_pipeline.warehouse.gcs import resolve_bucket

    settings = get_settings()
    bucket = resolve_bucket()
    prefix = str(settings.get("gcs", "reference_prefix", default=DEFAULT_REFERENCE_PREFIX)).strip(
        "/"
    )
    fs = gcsfs.GCSFileSystem(project=settings.get("gcp", "project", default=None) or None)
    written: list[str] = []
    for name in names:
        dst = f"{bucket}/{prefix}/{name}"
        fs.put_file(str(Path(local_dir) / name), dst)
        written.append(f"gs://{dst}")
    return written
