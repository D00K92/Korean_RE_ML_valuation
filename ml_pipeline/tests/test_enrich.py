"""Tests for 청약홈 enrichment — the leakage-guarded label join."""

from __future__ import annotations

import pandas as pd

from ml_pipeline.features.enrich import aggregate_competition, enrich_labels


def _applyhome():
    return pd.DataFrame(
        [
            # same complex, two 주택형 + a LATER phase that must be excluded by the guard
            dict(
                pblanc_no="A1",
                house_name="한강메트로자이(2단지)",
                supply_region="경기",
                exclusive_area_m2=59.9,
                supply_price_manwon=60000,
                notice_date=pd.Timestamp("2019-06-01"),
                move_in_ym="202112",
                total_units=1000,
                builder="GS건설",
            ),
            dict(
                pblanc_no="A1",
                house_name="한강메트로자이(2단지)",
                supply_region="경기",
                exclusive_area_m2=84.9,
                supply_price_manwon=90000,
                notice_date=pd.Timestamp("2019-06-01"),
                move_in_ym="202112",
                total_units=1000,
                builder="GS건설",
            ),
            dict(
                pblanc_no="A2",
                house_name="한강메트로자이",
                supply_region="경기",
                exclusive_area_m2=84.9,
                supply_price_manwon=99999,
                notice_date=pd.Timestamp("2023-01-01"),
                move_in_ym="202512",
                total_units=1000,
                builder="GS건설",
            ),
        ]
    )


def _labels():
    return pd.DataFrame(
        {
            "region_code": ["41570", "41570", "11110"],
            "complex_name": ["한강메트로자이2단지", "한강메트로자이2단지", "없는단지"],
            "exclusive_area_m2": [84.94, 59.75, 84.0],
            "deal_date": ["2020-03-01", "2020-03-01", "2021-01-01"],
            "price_per_m2": [1200, 1100, 900],
        }
    )


def test_enrich_picks_closest_area_and_respects_leakage_guard():
    out = enrich_labels(_labels(), _applyhome())
    m = out.set_index("complex_name")

    # 84.94㎡ row -> matches the 84.9 주택형's 분양가 (90000/84.9)
    row = out.iloc[0]
    assert row["ah_matched"]
    assert abs(row["ah_supply_price_per_m2"] - 90000 / 84.9) < 1e-6
    # LEAKAGE GUARD: the 2023 phase (A2) postdates the 2020 deal -> never chosen
    assert row["ah_pblanc_no"] == "A1"
    assert row["ah_notice_date"] <= pd.Timestamp("2020-03-01")

    # 59.75㎡ row -> picks the 59.9 주택형 (60000/59.9), not the 84.9 one
    assert abs(out.iloc[1]["ah_supply_price_per_m2"] - 60000 / 59.9) < 1e-6

    # months_to_completion = 202112 - 2020-03 = 21 months
    assert out.iloc[0]["ah_months_to_completion"] == 21

    # unmatched complex -> all enrichment null, matched False
    assert not m.loc["없는단지", "ah_matched"]
    assert pd.isna(m.loc["없는단지", "ah_supply_price_per_m2"])


def test_no_matched_row_violates_leakage_guard():
    out = enrich_labels(_labels(), _applyhome())
    ok = out[out["ah_matched"]]
    assert (ok["ah_notice_date"] <= pd.to_datetime(ok["deal_date"])).all()


# -- 경쟁률 aggregation + join ----------------------------------------------
def _competition():
    # PBLANC A1, 전용 84.9 (rounds to 85): supply 10, total 접수 250 -> rate 25;
    # a 미달 type (전용 59.9 -> 60): supply 20, 접수 8 -> rate 0.4 (undersubscribed)
    return pd.DataFrame(
        [
            dict(
                PBLANC_NO="A1",
                HOUSE_TY="084.9000",
                SUBSCRPT_RANK_CODE="1",
                RESIDE_SENM="해당지역",
                REQ_CNT="200",
                SUPLY_HSHLDCO="10",
            ),
            dict(
                PBLANC_NO="A1",
                HOUSE_TY="084.9000",
                SUBSCRPT_RANK_CODE="1",
                RESIDE_SENM="기타지역",
                REQ_CNT="50",
                SUPLY_HSHLDCO="10",
            ),
            dict(
                PBLANC_NO="A1",
                HOUSE_TY="059.9000",
                SUBSCRPT_RANK_CODE="1",
                RESIDE_SENM="해당지역",
                REQ_CNT="8",
                SUPLY_HSHLDCO="20",
            ),
        ]
    )


def test_aggregate_competition_rate_and_flags():
    agg = aggregate_competition(_competition()).set_index("area")
    # 84.9 -> area 85: (200+50)/10 = 25, local share 200/250 = 0.8, rank1 local 200/10 = 20
    assert agg.loc[85.0, "ah_competition_rate"] == 25.0
    assert not agg.loc[85.0, "ah_undersubscribed"]
    assert abs(agg.loc[85.0, "ah_local_demand_share"] - 0.8) < 1e-9
    assert agg.loc[85.0, "ah_rank1_local_rate"] == 20.0
    # 59.9 -> area 60: 8/20 = 0.4 -> undersubscribed
    assert agg.loc[60.0, "ah_undersubscribed"]


def test_enrich_attaches_competition_by_pblanc_and_area():
    out = enrich_labels(_labels(), _applyhome(), competition=_competition())
    # the 84.94㎡ row matched PBLANC A1 -> area 85 -> rate 25
    assert out.iloc[0]["ah_competition_rate"] == 25.0
    # unmatched complex -> competition null too
    assert pd.isna(out[out["complex_name"] == "없는단지"].iloc[0]["ah_competition_rate"])
