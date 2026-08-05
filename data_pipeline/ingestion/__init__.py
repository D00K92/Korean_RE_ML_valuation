"""Extractors for the four data sources.

Each module exposes a single-purpose, importable `extract()` function that
Airflow tasks and the Makefile call — no business logic lives in DAG files.
"""
