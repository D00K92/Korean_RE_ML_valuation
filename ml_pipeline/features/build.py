"""Assemble the unified feature matrix (property + spatial + macro + timing).

Importable entry point ``build_features()`` — called by the Vertex AI ``preprocess``
component (see ``ml_pipeline/components/preprocess.py``). Inputs are the raw
BigQuery contract tables (already read into DataFrames by the caller); the output
is the point-in-time feature matrix written back to the ``features`` table.

Invariant #1 (no look-ahead): every spatial/macro/applyhome join must respect the
reporting lag — a comp/enrichment is usable for a row only when it was publicly
reported/announced on or before that row's prediction date (see
``ml_pipeline.features.spatial.usable_comps`` and ``report_date``). The leakage
audit runs before the matrix is returned.
"""

from __future__ import annotations

import pandas as pd

from ml_pipeline.config import get_settings


def build_features(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build the unified training matrix from the raw BigQuery contract frames.

    ``raw`` maps logical table names (``molit_resale``, ``molit_apt_trade``,
    ``ecos_macro``, ``applyhome``, ``commercial``) to DataFrames read from
    BigQuery. Label = MOLIT resale price/㎡. Features are assembled point-in-time;
    every spatial/macro join respects the reporting lag.

    The individual feature transforms already live in ``ml_pipeline.features.*``
    (``property``, ``spatial``, ``macro``, ``enrich``, ``comps``); this function
    is their point-in-time assembly + leakage audit, which is the remaining ML
    work. It is intentionally not yet wired end-to-end.
    """
    _ = get_settings()
    _ = raw
    raise NotImplementedError(
        "build_features: point-in-time assembly of the feature transforms is the "
        "remaining ML work (transforms exist in ml_pipeline.features.*)."
    )
