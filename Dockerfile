# Astro Runtime image for local Apache Airflow (data pillar / ingest DAGs).
# `astro dev start` builds this; the base image already bundles Apache Airflow.
FROM quay.io/astronomer/astro-runtime:12.7.0

# Make the repo importable so DAGs can `from data_pipeline... import ...`, and
# point Airflow at the pillar's dags/ folder (they don't live in ./dags).
ENV PYTHONPATH=/usr/local/airflow
ENV AIRFLOW__CORE__DAGS_FOLDER=/usr/local/airflow/data_pipeline/dags

# GCP auth for the GCS mirror + BigQuery load tasks. The file is an Application
# Default Credentials credential (the org policy disables downloadable SA keys),
# baked into this local dev image with the rest of data_pipeline/ (gitignored,
# never pushed). Astro only bind-mounts ./dags|include|plugins, so data_pipeline/
# — DAGs and this cred — is baked via the build, not mounted.
ENV GOOGLE_APPLICATION_CREDENTIALS=/usr/local/airflow/data_pipeline/secrets/gcp-sa.json

# Install the data-pillar Python deps. The base image installs the root
# requirements.txt earlier in its ONBUILD sequence — before the project is copied
# in — so the pillar's own requirements.txt (the single source of truth) can only
# be installed here, after that COPY has landed data_pipeline/ in the image.
USER root
RUN pip install --no-cache-dir -r data_pipeline/requirements.txt
USER astro
