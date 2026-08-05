"""Tests for commercial (상가) preprocessing."""

from __future__ import annotations

import pandas as pd

from ml_pipeline.features.comps import preprocess_raw_commercial


def _raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bizesId": ["A", "B", "C"],
            "bizesNm": ["가게1", "가게2", "가게3"],
            "brchNm": ["", "지점", ""],
            "indsLclsNm": ["소매", "음식", "소매"],
            "indsLclsCd": ["G2", "I2", "G2"],
            "signguCd": ["11680", "11680", "11680"],
            "ldongCd": ["1168010100"] * 3,
            "adongCd": ["1168064000"] * 3,
            "indsMclsCd": ["", "", ""],
            "indsMclsNm": ["", "", ""],
            "indsSclsCd": ["", "", ""],
            "indsSclsNm": ["", "", ""],
            "ksicCd": ["", "", ""],
            "ksicNm": ["", "", ""],
            "lnoAdr": ["a", "b", "c"],
            "rdnmAdr": ["a", "b", "c"],
            "lat": ["37.5", "0", "37.6"],  # middle row has invalid coord
            "lon": ["127.0", "0", "127.1"],
            "region": ["11680"] * 3,
        }
    )


def test_coords_cast_and_invalid_dropped():
    out = preprocess_raw_commercial(_raw())
    assert out["lat"].dtype == "float64"
    assert len(out) == 2  # the (0,0) coord row is dropped
    assert set(out["bizesId"]) == {"A", "C"}


def test_empty_strings_become_null():
    out = preprocess_raw_commercial(_raw())
    # brchNm '' -> NA; the kept rows A and C both had empty brchNm
    assert out["brchNm"].isna().all()


def test_full_upjong_hierarchy_kept():
    out = preprocess_raw_commercial(_raw())
    for col in ["indsLclsNm", "indsMclsNm", "indsSclsNm", "ksicNm"]:
        assert col in out.columns
