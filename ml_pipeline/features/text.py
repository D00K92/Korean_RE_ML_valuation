"""Name normalizers for cross-source feature matching (ML-pillar owned).

`base_name` reduces a complex/apt name to a marker-free base so a 청약홈
announcement can be matched to a MOLIT label row. It is a pure string function
with no warehouse or ingestion dependencies, kept here so `ml_pipeline` imports
nothing from `data_pipeline` (the BigQuery tables are the only pillar boundary).

`data_pipeline.ingestion.geocoding` carries an equivalent normalizer for the
ingestion-side geocoder; the two are intentionally independent per-pillar copies
of the same 8-line rule, not a shared import.
"""

from __future__ import annotations

import re
import unicodedata


def base_name(name: str | None) -> str:
    """Reduce a complex/apt name to a marker-free base for cross-source matching.

    NFKC first (full-width `２차`/`　` were silently breaking matches), then strip
    parentheticals, block codes (A2, C-3블록, B9), and 단지/차/블록 suffixes.
    """
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[A-Z]{1,3}-?\d+(-\d+)?\s*(블[록럭]|BL)?", " ", s)
    s = re.sub(r"\d+\s*(단지|차|회|블[록럭]|BL)", " ", s)
    s = re.sub(r"(블[록럭]|BL)\s*[A-Z]?-?\d*", " ", s)
    return re.sub(r"\s+", "", s)
