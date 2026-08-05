"""ML pipeline component: model training + Vertex AI experiment logging.

Trains a regressor for realized resale price/㎡ on the time-based split
(invariant #2 — never shuffle) and logs params + metrics to Vertex AI
Experiments. Model family is selectable (``config.yaml`` ``vertex.model_family``
or the ``model_family`` arg): LightGBM, XGBoost, or scikit-learn
HistGradientBoosting — all three are in scope.

Reads the ``features`` table from BigQuery (produced by the ``preprocess``
component). GCP auth is ADC; Vertex logging is best-effort and skipped cleanly
when aiplatform / a project are unavailable, so the fit itself always runs.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from ml_pipeline.components.evaluate import all_metrics
from ml_pipeline.components.split import time_based_split
from ml_pipeline.config import get_settings

logger = logging.getLogger(__name__)

# default label column name the feature build emits (KRW per m²)
DEFAULT_LABEL_COL = "price_per_m2"


def _make_model(family: str, params: dict[str, Any]):
    """Instantiate a regressor for the selected model family."""
    if family == "lightgbm":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(**params)
    if family == "xgboost":
        from xgboost import XGBRegressor

        return XGBRegressor(**params)
    if family in ("sklearn_hgb", "sklearn"):
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(**params)
    raise ValueError(f"unknown model_family {family!r} (expected lightgbm | xgboost | sklearn_hgb)")


def _feature_columns(df: pd.DataFrame, label_col: str) -> list[str]:
    """Numeric feature columns = all numeric columns except the label."""
    numeric = df.select_dtypes(include="number").columns.tolist()
    return [c for c in numeric if c != label_col]


def _log_to_vertex(
    family: str, params: dict[str, Any], metrics: dict[str, float], n_features: int
) -> None:
    """Best-effort: log params + metrics to a Vertex AI Experiments run."""
    try:
        from google.cloud import aiplatform
    except ImportError:
        logger.warning("google-cloud-aiplatform not installed; skipping Vertex logging")
        return
    s = get_settings()
    project = s.get("gcp", "project", default="") or None
    if not project:
        logger.warning("no GCP project configured; skipping Vertex experiment logging")
        return
    aiplatform.init(
        project=project,
        location=s.get("gcp", "region", default="asia-northeast3"),
        experiment=s.get("vertex", "experiment", default="presale_resale_price"),
    )
    run = aiplatform.start_run(run=f"{family}-run")
    run.log_params({"model_family": family, "n_features": n_features, **params})
    run.log_metrics(metrics)
    aiplatform.end_run()
    logger.info("logged run to Vertex AI experiment %s", s.get("vertex", "experiment"))


def train(
    df: pd.DataFrame | None = None,
    *,
    label_col: str = DEFAULT_LABEL_COL,
    date_col: str = "deal_date",
    model_family: str | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Time-split, fit the selected model family, evaluate on the held-out test slice.

    ``df`` defaults to the ``features`` BigQuery table. Metrics (RMSE/MAPE/R²) are
    computed on the most-recent test slice only (invariant #2). Returns a summary
    dict; also logs to Vertex AI Experiments when configured.
    """
    s = get_settings()
    family = model_family or s.get("vertex", "model_family", default="lightgbm")
    params = params or {}

    if df is None:
        from ml_pipeline import bq

        df = bq.read_table("features")

    split = time_based_split(
        df,
        date_col=date_col,
        val_fraction=float(s.get("split", "val_fraction", default=0.15)),
        test_fraction=float(s.get("split", "test_fraction", default=0.15)),
    )
    feats = _feature_columns(df, label_col)
    if not feats:
        raise ValueError("no numeric feature columns found in the feature matrix")

    model = _make_model(family, params)
    model.fit(split.train[feats], split.train[label_col])
    test_pred = model.predict(split.test[feats])
    metrics = all_metrics(split.test[label_col].to_numpy(), test_pred)

    logger.info("%s test metrics: %s", family, metrics)
    _log_to_vertex(family, params, metrics, len(feats))
    return {
        "model_family": family,
        "metrics": metrics,
        "n_features": len(feats),
        "n_train": len(split.train),
        "n_test": len(split.test),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    train()
