# Repository Architecture & Coding Guidelines for AI Agents

Welcome Agent! You are working on a production-grade **Korean Real Estate MLOps Pipeline** project. 

Your goal is to help build data ingestion, feature engineering, and model training logic while strictly adhering to the repository architecture, coding conventions, and platform boundaries defined below.

---

## 1. Repository Directory Structure

You MUST maintain and enforce this directory layout. **Do NOT create top-level files or arbitrary folders outside this structure.**

```text
korea-real-estate-mlops/
├── .github/
│   └── workflows/              # CI/CD Workflows (GitHub Actions)
│       ├── deploy_data_dag.yaml
│       └── deploy_ml_pipeline.yaml
│
├── data_pipeline/              # DATA PILLAR (Ingestion & Warehousing)
│   ├── dags/                   # Local Airflow DAG definitions
│   │   └── daily_ingestion_dag.py
│   └── sql/                    # BigQuery SQL queries & DDL transformations
│       └── historical_features.sql
│
├── ml_pipeline/                # ML PILLAR (Preprocessing, Training, Evaluation)
│   ├── components/             # Modular Python execution scripts / KFP steps
│   │   ├── preprocess.py       # BigQuery extraction & feature generation
│   │   ├── train.py            # LightGBM/XGBoost training step
│   │   └── evaluate.py         # Model validation & metrics generation
│   ├── pipeline.py             # Vertex AI / Kubeflow Pipeline orchestration
│   └── requirements.txt        # ML dependencies (lightgbm, pandas, kfp, etc.)
│
├── notebooks/                  # SANDBOX ONLY (Ignored by CI/CD)
│   └── eda_experimentation.ipynb
│
├── AGENT_INSTRUCTIONS.md       # This file
├── config.yaml                 # Central project configuration (GCP IDs, paths)
└── README.md                   # Project overview and run instructions
```

## 2. Core Separation Principles
1. Data Pipeline vs. ML Pipeline Boundary:

* data_pipeline/ owns Ingestion and Raw Storage. It collects external daily updates, formats them into Hive-partitioned Parquet files on GCS (gs://.../raw/dt=YYYY-MM-DD/), and loads them into BigQuery.

* ml_pipeline/ owns Feature Extraction, Training, and Evaluation. It queries BigQuery tables, builds feature matrices, trains ML models (LightGBM/XGBoost), logs metrics, and outputs model artifacts to GCS.

* Contract: BigQuery tables (korea_real_estate.*) act as the explicit boundary between the Data Pipeline and ML Pipeline.

2. No Monolithic Notebooks in Production:

* Notebooks in notebooks/ are strictly for quick Exploratory Data Analysis (EDA).

* Never place core ETL, preprocessing, or training logic solely inside Jupyter Notebooks.

* All production code must be written as modular, typed Python scripts (.py) inside data_pipeline/ or ml_pipeline/.

## 3. Tech Stack & Library Rules
* Orchestration: Local Apache Airflow (via Astro CLI) for Data Ingestion; Vertex AI Pipelines (Kubeflow Pipelines SDK v2) for ML Workflows.

* Storage & Warehouse: Google Cloud Storage (GCS) for Parquet files; Google BigQuery for SQL analytics.

* ML Stack: Python 3.10+, lightgbm, xgboost, pandas, pyarrow, google-cloud-bigquery, google-cloud-storage.

## 4. Coding Conventions for Agents
When generating Python scripts or modifying code, adhere strictly to these rules:

A. Environment & Credentials Handling
NEVER hardcode GCP Service Account JSON keys, API keys, or credentials into source files.

Use google.auth.default() or standard GCP SDK clients (storage.Client(), bigquery.Client()) assuming Application Default Credentials (ADC) are configured.

Pull dynamic variables (Project ID, Bucket Name, Dataset ID) from config.yaml or environment variables:

```Python
import os
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-gcp-project-id")
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "your-mlops-bucket-name")
B. Type Hinting & Docstrings
All Python functions must include explicit type hints and concise docstrings.
```

Example:

```Python
def extract_features(project_id: str, start_date: str) -> pd.DataFrame:
    """Extracts raw trade data from BigQuery and computes engineered features.

    Args:
        project_id: GCP Project ID.
        start_date: Filter date in 'YYYY-MM-DD' format.

    Returns:
        Pandas DataFrame containing features and target variable.
    """
    # Implementation...
```
C. BigQuery SQL Execution
* Keep raw SQL strings inside data_pipeline/sql/*.sql files whenever possible, or embed clear parameterised queries using Python string formatting or bigquery.QueryJobConfig.

* Always use explicit column lists in SELECT statements (avoid SELECT * in production pipelines).

5. Agent Verification Checklist
Before submitting or suggesting code changes, verify:

[ ] Is the new or modified file located in the correct directory (data_pipeline/, ml_pipeline/, etc.)?

[ ] Are all credential keys and GCP secrets kept out of code and added to .gitignore?

[ ] Do functions include type annotations and error handling?

[ ] Does the ML code read cleanly from BigQuery / GCS without duplicating raw ingestion logic?