"""DAG integrity tests: every DAG loads without import errors, is tagged, and
sets task retries >= 2. Adapted from the Astro `astro dev init` example so it
lives with the rest of the data-pillar tests instead of a root `tests/` folder.

Airflow is only installed in the Astro Runtime image, not the local uv/test env,
so this module is skipped by `make test` and exercised inside the container
(`astro dev pytest`). The DagBag is read from AIRFLOW__CORE__DAGS_FOLDER, which
the Dockerfile points at data_pipeline/dags/.
"""

import logging
import os
from contextlib import contextmanager

import pytest

pytest.importorskip("airflow", reason="airflow only present in the Astro image")

from airflow.models import DagBag  # noqa: E402


@contextmanager
def suppress_logging(namespace):
    logger = logging.getLogger(namespace)
    old_value = logger.disabled
    logger.disabled = True
    try:
        yield
    finally:
        logger.disabled = old_value


def get_import_errors():
    """Generate a tuple for import errors in the dag bag."""
    with suppress_logging("airflow"):
        dag_bag = DagBag(include_examples=False)

        def strip_path_prefix(path):
            return os.path.relpath(path, os.environ.get("AIRFLOW_HOME"))

        # prepend "(None,None)" to ensure a test object always exists, even as a no-op.
        return [(None, None)] + [
            (strip_path_prefix(k), v.strip()) for k, v in dag_bag.import_errors.items()
        ]


def get_dags():
    """Generate a tuple of dag_id, <DAG objects> in the DagBag."""
    with suppress_logging("airflow"):
        dag_bag = DagBag(include_examples=False)

    def strip_path_prefix(path):
        return os.path.relpath(path, os.environ.get("AIRFLOW_HOME"))

    return [(k, v, strip_path_prefix(v.fileloc)) for k, v in dag_bag.dags.items()]


@pytest.mark.parametrize(
    "rel_path,rv", get_import_errors(), ids=[x[0] for x in get_import_errors()]
)
def test_file_imports(rel_path, rv):
    """Test for import errors on a file."""
    if rel_path and rv:
        raise Exception(f"{rel_path} failed to import with message \n {rv}")


APPROVED_TAGS = {}


@pytest.mark.parametrize("dag_id,dag,fileloc", get_dags(), ids=[x[2] for x in get_dags()])
def test_dag_tags(dag_id, dag, fileloc):
    """Test that a DAG is tagged and those tags are in the approved list."""
    assert dag.tags, f"{dag_id} in {fileloc} has no tags"
    if APPROVED_TAGS:
        assert not set(dag.tags) - APPROVED_TAGS


@pytest.mark.parametrize("dag_id,dag,fileloc", get_dags(), ids=[x[2] for x in get_dags()])
def test_dag_retries(dag_id, dag, fileloc):
    """Test that a DAG has task retries >= 2."""
    assert (
        dag.default_args.get("retries", None) >= 2
    ), f"{dag_id} in {fileloc} must have task retries >= 2."
