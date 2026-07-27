"""Assemble the unified feature matrix (property + spatial + macro + timing).

Importable entry point `build_features()` — called by the Makefile and the
Airflow feature_build task. Runs the leakage audit before writing.
"""

from __future__ import annotations

import pandas as pd

from presale.config import get_settings


def build_features() -> pd.DataFrame:
    """Build and persist the unified training matrix.

    Label = MOLIT resale price/㎡. Features assembled point-in-time; every
    spatial/macro join respects the reporting lag. Writes to feature_dir.
    """
    _ = get_settings()
    raise NotImplementedError("build_features not yet implemented")


if __name__ == "__main__":
    build_features()
