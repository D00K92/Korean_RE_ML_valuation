"""Tests for the bundled 법정동코드 reference table parsing/hierarchy derivation."""

from __future__ import annotations

import pytest

from presale.storage.reference import (
    LEGAL_DONG_TXT,
    LegalDongResolver,
    load_legal_dong_frame,
    normalize_dong_name,
)


@pytest.fixture(scope="module")
def resolver() -> LegalDongResolver:
    return LegalDongResolver()


def test_legal_dong_frame_structure_and_hierarchy():
    df = load_legal_dong_frame()
    assert {"code", "name", "is_active", "sido_code", "sigungu_code", "emd_code", "level"} <= set(
        df.columns
    )
    # every code is a 10-digit string
    assert df["code"].str.fullmatch(r"\d{10}").all()

    by_code = df.set_index("code")
    # 시도 / 시군구 / 읍면동 level derivation on known Seoul codes
    assert by_code.loc["1100000000", "level"] == "시도"
    assert by_code.loc["1111000000", "level"] == "시군구"
    assert by_code.loc["1111000000", "sigungu_code"] == "11110"
    assert by_code.loc["1111010100", "level"] == "읍면동"  # 종로구 청운동
    assert by_code.loc["1111010100", "sigungu_code"] == "11110"


def test_reference_source_is_committed():
    # the DuckDB table is rebuilt from this committed txt on a fresh clone
    assert LEGAL_DONG_TXT.exists()


def test_normalize_dong_name_strips_suffix_and_takes_last_token():
    assert normalize_dong_name("고산동") == "고산"
    assert normalize_dong_name("고산리") == "고산"  # 동/리 rename collapses to same stem
    assert normalize_dong_name("모현읍 왕산리") == "왕산"  # last token, suffix stripped
    assert normalize_dong_name("") == ""


def test_resolver_matches_simple_dong(resolver: LegalDongResolver):
    assert resolver.resolve("11680", "삼성동") == "1168010500"  # 강남 삼성동
    assert resolver.resolve("11110", "청운동") == "1111010100"  # 종로 청운동


def test_resolver_handles_reorganization_renames(resolver: LegalDongResolver):
    # names that drifted after the reference snapshot must still resolve
    assert resolver.resolve("41461", "모현읍 왕산리") == "4146131021"  # 면→읍
    assert resolver.resolve("41610", "고산동") == "4161025021"  # 리→동
    assert resolver.resolve("41220", "고덕동") == "4122033000"  # 면→동


def test_resolver_is_null_safe(resolver: LegalDongResolver):
    # a miss returns None (caller falls back to 시군구) — never raises, never guesses
    assert resolver.resolve("11680", None) is None
    assert resolver.resolve("11680", "존재하지않는동") is None
