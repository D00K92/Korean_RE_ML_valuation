"""Config loader for the ML pillar.

Reads the same root ``config.yaml`` as the data pillar but exposes only the
non-secret tunables the ML pipeline needs (BigQuery dataset, split fractions,
feature windows, Vertex settings). The ML pillar authenticates to GCP via
Application Default Credentials (``google.auth.default()``) and reads its inputs
from BigQuery — it holds no gov-API secrets and never re-ingests raw data.

GCP identifiers are env-overridable so Vertex/CI deploys don't edit config:
``GCP_PROJECT_ID``, ``GCS_BUCKET``, ``BQ_DATASET``, ``VERTEX_PIPELINE_ROOT``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_YAML = PROJECT_ROOT / "config.yaml"

# env var -> (yaml section, key) it overrides
_ENV_OVERRIDES = {
    "GCP_PROJECT_ID": ("gcp", "project"),
    "GCS_BUCKET": ("gcs", "bucket"),
    "BQ_DATASET": ("bigquery", "dataset"),
    "VERTEX_PIPELINE_ROOT": ("vertex", "pipeline_root"),
}


class Settings:
    """Read-only view over root ``config.yaml`` with GCP env overrides applied."""

    def __init__(self) -> None:
        with open(CONFIG_YAML, encoding="utf-8") as fh:
            self.yaml: dict[str, Any] = yaml.safe_load(fh)
        for env_name, (section, key) in _ENV_OVERRIDES.items():
            val = os.environ.get(env_name)
            if val:
                self.yaml.setdefault(section, {})[key] = val

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.yaml
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def bq_table(self, name: str) -> str:
        """Fully-qualified ``project.dataset.table`` for a logical table name."""
        project = self.get("gcp", "project", default="")
        dataset = self.get("bigquery", "dataset", default="korea_real_estate")
        table = self.get("bigquery", "tables", name, default=name)
        prefix = f"{project}." if project else ""
        return f"{prefix}{dataset}.{table}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
