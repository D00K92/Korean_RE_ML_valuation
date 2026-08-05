"""Tests for 학군 (school-quality) features: schoolinfo⨝geocoded + proximity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml_pipeline.features.spatial import (
    add_school_quality_features,
    build_selective_schools,
)

_M_PER_DEG_LAT = np.pi / 180 * 6_371_000.0


def _schoolinfo():
    return pd.DataFrame(
        [
            dict(name="한일외국어고", hs_type="특수목적고등학교", grad_rate=95.0),
            dict(name="세종자율고", hs_type="자율고등학교", grad_rate=90.0),
            dict(name="보통고", hs_type="일반고등학교", grad_rate=80.0),  # not selective
            dict(name="좌표없는특목고", hs_type="특수목적고등학교", grad_rate=99.0),  # no geo match
        ]
    )


def _geocoded():
    # only the first two selective schools have coords in the NEIS set
    return pd.DataFrame(
        {
            "name": ["한일외국어고", "세종자율고", "보통고"],
            "lat": [37.5, 37.5 + 900 / _M_PER_DEG_LAT, 37.6],
            "lon": [127.0, 127.0, 127.2],
        }
    )


def test_build_selective_filters_type_and_joins_coords():
    sel = build_selective_schools(_schoolinfo(), _geocoded())
    # 일반고 excluded; 좌표없는 특목고 dropped (no coord match) -> 2 remain
    assert set(sel["name"]) == {"한일외국어고", "세종자율고"}
    assert sel["lat"].notna().all()


def test_proximity_features():
    sel = build_selective_schools(_schoolinfo(), _geocoded())
    props = pd.DataFrame({"lat": [37.5, np.nan], "lon": [127.0, np.nan]})
    out = add_school_quality_features(props, sel, radii_m=(1000,))
    # P0 on top of 한일외고 -> ~0 m; both selective schools within 1000m (~900m apart)
    assert out.loc[0, "nearest_selective_hs_dist_m"] < 1.0
    assert out.loc[0, "n_selective_hs_within_1000m"] == 2
    # coordless row stays NaN
    assert pd.isna(out.loc[1, "nearest_selective_hs_dist_m"])
