# Astro Runtime image for local Apache Airflow (data pillar / ingest DAGs).
# `astro dev start` builds this; the base image already bundles Apache Airflow.
FROM quay.io/astronomer/astro-runtime:12.7.0

# Make the repo importable so DAGs can `from data_pipeline... import ...`, and
# point Airflow at the pillar's dags/ folder (they don't live in ./dags).
ENV PYTHONPATH=/usr/local/airflow
ENV AIRFLOW__CORE__DAGS_FOLDER=/usr/local/airflow/data_pipeline/dags

# GCP auth for the GCS mirror + BigQuery load tasks (ADC via a mounted SA key).
ENV GOOGLE_APPLICATION_CREDENTIALS=/usr/local/airflow/secrets/gcp-sa.json
