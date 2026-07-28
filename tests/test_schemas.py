"""Schema tests for extractor pydantic models."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from presale.schemas import MolitResaleRecord


def _valid_kwargs() -> dict:
    return dict(
        region_code="41135",
        dong="정자동",
        complex_name="테스트단지",
        exclusive_area_m2="84.9987",  # floored DOWN to 2 d.p. -> 84.99
        floor=12,
        deal_year=2024,
        deal_month=3,
        deal_day=15,
        price_manwon="120,000",  # dealAmount kept in 만원 (sector standard), commas stripped
        right_type="입",  # ownershipGbn '입' → 입주권
    )


def test_valid_record_parses_and_derives_label():
    rec = MolitResaleRecord(**_valid_kwargs())
    assert rec.price_manwon == 120_000  # 만원, no ×10,000
    assert rec.exclusive_area_m2 == 84.99  # floored down from 84.9987
    assert rec.right_type == "입주권"
    assert rec.deal_date == dt.date(2024, 3, 15)
    assert rec.price_per_m2 == pytest.approx(120_000 / 84.99)  # 만원/㎡


def test_area_is_floored_not_rounded():
    kw = _valid_kwargs()
    kw["exclusive_area_m2"] = "112.8599"  # must floor to 112.85, never round to 112.86
    assert MolitResaleRecord(**kw).exclusive_area_m2 == 112.85


def test_impossible_date_rejected():
    kw = _valid_kwargs()
    kw.update(deal_month=2, deal_day=30)
    with pytest.raises(ValidationError):
        MolitResaleRecord(**kw)


def test_nonpositive_area_rejected():
    kw = _valid_kwargs()
    kw["exclusive_area_m2"] = 0
    with pytest.raises(ValidationError):
        MolitResaleRecord(**kw)
