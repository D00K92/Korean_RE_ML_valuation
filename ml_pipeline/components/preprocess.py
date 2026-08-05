"""ML pipeline component: BigQuery extraction + feature generation.

Reads the raw ``korea_real_estate.*`` contract tables the data pillar produced,
assembles the point-in-time feature matrix (``ml_pipeline.features.build``), and
writes it back as the ``features`` table — the input to ``train``. This is the
first step of the Vertex AI / KFP pipeline (see ``ml_pipeline/pipeline.py``).

Reads only from BigQuery (never re-ingests, never imports ``data_pipeline``).
"""

from __future__ import annotations

import logging

import pandas as pd

from ml_pipeline import bq
from ml_pipeline.features.build import build_features

logger = logging.getLogger(__name__)

# Raw contract tables the feature build consumes (logical names -> BQ tables via
# config ``bigquery.tables``). Kept explicit so a missing source fails loudly.
RAW_SOURCES = ["molit_resale", "molit_apt_trade", "ecos_macro", "applyhome", "commercial"]


def load_raw_tables(sources: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Read each raw contract table from BigQuery into a DataFrame."""
    names = sources or RAW_SOURCES
    frames: dict[str, pd.DataFrame] = {}
    for name in names:
        frames[name] = bq.read_table(name)
        logger.info("read %s: %d rows", name, len(frames[name]))
    return frames


def run(output_table: str = "features") -> str:
    """Assemble the feature matrix from BigQuery and write it back to BigQuery.

    Returns the fully-qualified output table ref. This is the plain-Python entry
    point; ``ml_pipeline.pipeline`` wraps it as a containerized KFP component.
    """
    raw = load_raw_tables()
    features = build_features(raw)
    return bq.write_table(features, output_table)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
