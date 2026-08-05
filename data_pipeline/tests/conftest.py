"""Pytest configuration — run the suite fully offline.

Reference lookups (法定동 codes, transit coords) are GCS-backed at runtime, but
the tests must not touch the cloud. Setting ``REFERENCE_DIR`` makes
``refstore.reference_path`` resolve to the committed subsets in
``tests/fixtures/reference`` instead of downloading from GCS.
"""

import os
import pathlib

os.environ.setdefault(
    "REFERENCE_DIR", str(pathlib.Path(__file__).parent / "fixtures" / "reference")
)
