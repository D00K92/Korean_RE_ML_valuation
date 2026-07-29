"""Schema tests for NEIS SchoolRecord."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from presale.schemas import SchoolRecord


def _kw() -> dict:
    return dict(
        school_code="7010057",
        name="가락고등학교",
        school_type="고등학교",
        foundation="공립",
        office="서울특별시교육청",
        sido="서울특별시",
        road_address="서울특별시 송파구 송이로 42",
        road_address_detail="(송파동,가락고등학교)",
        coedu="남여공학",
    )


def test_valid_school_parses():
    s = SchoolRecord(**_kw())
    assert s.school_type == "고등학교"
    assert s.road_address == "서울특별시 송파구 송이로 42"


def test_missing_road_address_rejected():
    kw = _kw()
    kw["road_address"] = ""  # can't geocode -> must drop
    with pytest.raises(ValidationError):
        SchoolRecord(**kw)


def test_whitespace_name_rejected():
    kw = _kw()
    kw["name"] = "   "
    with pytest.raises(ValidationError):
        SchoolRecord(**kw)
