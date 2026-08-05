"""Schema tests for the 청약홈 분양정보 ApplyhomeRecord model."""

from __future__ import annotations

from data_pipeline.schemas.applyhome import ApplyhomeRecord


# -- 전용 parsed from HOUSE_TY (floored), price in 만원 --------------------------
def test_area_parsed_from_house_type_not_supply_ar():
    r = ApplyhomeRecord(
        pblanc_no="2023000001",
        house_name="테스트자이",
        notice_date="2023-05-01",
        house_type="084.9600A",
        exclusive_area_m2="084.9600A",
        supply_price_manwon="70,000",
    )
    assert r.exclusive_area_m2 == 84.96  # floored 2dp from HOUSE_TY, NOT 공급면적
    assert r.supply_price_manwon == 70000
