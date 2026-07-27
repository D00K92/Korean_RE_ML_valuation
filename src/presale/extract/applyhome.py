"""Applyhome (청약홈) extractor — INFERENCE LIST ONLY.

Produces the "upcoming launches to score" list (base price + area) for the
dashboard. This data MUST NEVER enter training — it is not a label source.
See CLAUDE.md invariant #3.
"""

from __future__ import annotations

import pandas as pd


def extract() -> pd.DataFrame:
    """Fetch upcoming launches to score. Inference-only; never joined to labels.

    TODO: Applyhome API call (tenacity retry), pydantic validation, land to a
    dedicated inference table kept separate from the training feature layer.
    """
    raise NotImplementedError("Applyhome extract not yet implemented")


if __name__ == "__main__":
    extract()
