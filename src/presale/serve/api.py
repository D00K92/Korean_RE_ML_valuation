"""FastAPI service. Loads the model from the MLflow registry (by stage/version),
not from a loose pickle.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Presale Rights Resale-Price API", version="0.1.0")


class PredictRequest(BaseModel):
    exclusive_area_m2: float
    floor: int | None = None
    building_age_years: float | None = None
    # ... remaining feature fields filled in once the matrix is finalized


class PredictResponse(BaseModel):
    price_per_m2: float
    model_version: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    """Score one property. TODO: load registered model + build feature vector."""
    raise NotImplementedError("predict endpoint not yet wired to the registry")
