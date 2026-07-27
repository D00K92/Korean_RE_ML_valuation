"""LightGBM training + MLflow logging/registry (LightGBM only — no ensembles).

Importable `train()` — called by the Makefile and the Airflow train task.
Logs params, metrics (RMSE/MAPE/R²), and feature importance every run, and
registers the model to the MLflow Model Registry.
"""

from __future__ import annotations

from presale.config import get_settings
from presale.train.split import time_based_split


def train() -> str:
    """Train on the time-based split, log to MLflow, register the model.

    Returns the registered model version/URI. TODO: load feature matrix,
    time_based_split, fit LightGBM, evaluate on the held-out test slice, log +
    register.
    """
    settings = get_settings()
    _ = settings.get("split", default={})
    _ = time_based_split  # used once the feature matrix exists
    raise NotImplementedError("train not yet implemented")


if __name__ == "__main__":
    train()
