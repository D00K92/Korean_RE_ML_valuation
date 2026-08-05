"""Vertex AI Pipeline (KFP SDK v2): preprocess -> train.

Orchestrates the ML pillar on Vertex AI Pipelines. Each step is a KFP component
that calls the same importable ``ml_pipeline`` functions used by the Makefile and
tests — no business logic lives here (mirrors the Airflow "DAG orchestrates, does
not compute" rule on the data side).

Steps:
    preprocess_op  -> reads the BigQuery contract tables, builds the feature
                      matrix, writes it back as the ``features`` table.
    train_op       -> time-splits, fits the selected model family, evaluates on
                      the held-out test slice (metrics via
                      ``ml_pipeline.components.evaluate``), logs to Vertex AI
                      Experiments.

The component base image must have this repo installed (``pip install .`` +
``uv sync --group ml``); set it via the ``ML_PIPELINE_IMAGE`` env var. Compile
with ``compile_pipeline()`` and submit with ``submit()`` (google-cloud-aiplatform).

NOTE: no ``from __future__ import annotations`` here — KFP's component parser
resolves real type objects from the signature, and PEP 563 stringized
annotations break it.
"""

import os

from kfp import compiler, dsl

from ml_pipeline.config import get_settings

# Container image with ml_pipeline + deps installed (built from this repo).
BASE_IMAGE = os.environ.get("ML_PIPELINE_IMAGE", "python:3.11")


@dsl.component(base_image=BASE_IMAGE)
def preprocess_op(output_table: str) -> str:
    """Build the feature matrix from BigQuery and write it back. Returns table ref."""
    from ml_pipeline.components.preprocess import run

    return run(output_table=output_table)


@dsl.component(base_image=BASE_IMAGE)
def train_op(features_table: str, model_family: str, metrics: dsl.Output[dsl.Metrics]) -> None:
    """Train the selected model family on the feature table; emit test metrics."""
    from ml_pipeline import bq
    from ml_pipeline.components.train import train

    df = bq.read_table("features")
    summary = train(df, model_family=model_family)
    for name, value in summary["metrics"].items():
        metrics.log_metric(name, float(value))


@dsl.pipeline(name="presale-resale-price", description="Korean pre-sale resale price/㎡")
def pipeline(model_family: str = "lightgbm", output_table: str = "features") -> None:
    features = preprocess_op(output_table=output_table)
    train_op(features_table=features.output, model_family=model_family)


def compile_pipeline(package_path: str = "presale_pipeline.json") -> str:
    """Compile the pipeline to a JSON spec for Vertex AI. Returns the path."""
    compiler.Compiler().compile(pipeline_func=pipeline, package_path=package_path)
    return package_path


def submit(package_path: str = "presale_pipeline.json", *, sync: bool = False) -> str:
    """Compile (if needed) and submit the pipeline to Vertex AI Pipelines.

    Uses ADC + ``config.yaml`` (``gcp`` / ``vertex``). Returns the pipeline job
    resource name. ``pipeline_root`` (a GCS path) must be configured.
    """
    from google.cloud import aiplatform

    s = get_settings()
    project = s.get("gcp", "project", default="") or None
    pipeline_root = s.get("vertex", "pipeline_root", default="") or None
    if not (project and pipeline_root):
        raise ValueError("gcp.project and vertex.pipeline_root must be configured to submit")

    if not os.path.exists(package_path):
        compile_pipeline(package_path)

    aiplatform.init(project=project, location=s.get("gcp", "region", default="asia-northeast3"))
    job = aiplatform.PipelineJob(
        display_name=s.get("vertex", "model_display_name", default="presale_resale"),
        template_path=package_path,
        pipeline_root=pipeline_root,
        parameter_values={"model_family": s.get("vertex", "model_family", default="lightgbm")},
    )
    job.submit()
    return job.resource_name


if __name__ == "__main__":
    print(compile_pipeline())
