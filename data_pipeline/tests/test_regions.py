"""Unit tests for Settings.select_regions — the single CLI region-selector used
by data_pipeline/scripts/backfill.py and geocode.py (replaces the per-script filters)."""

from __future__ import annotations

from data_pipeline.config import _NAMED_REGION_CODES, get_settings


def test_all_matches_resolve_lawd_codes():
    s = get_settings()
    assert s.select_regions("all") == s.resolve_lawd_codes()


def test_named_hwaseong_bucheon_returns_the_seven_gu_codes():
    s = get_settings()
    assert s.select_regions("hwaseong_bucheon") == _NAMED_REGION_CODES["hwaseong_bucheon"]


def test_explicit_five_digit_codes_pass_through():
    s = get_settings()
    assert s.select_regions("41192,41194") == ["41192", "41194"]


def test_seoul_alias_filters_to_prefix_11():
    s = get_settings()
    seoul = s.select_regions("seoul")
    assert seoul, "expected some Seoul codes in the configured scope"
    assert all(c.startswith("11") for c in seoul)
    assert set(seoul).issubset(set(s.resolve_lawd_codes()))


def test_bare_prefix_filters_configured_scope():
    s = get_settings()
    gg = s.select_regions("41")
    assert all(c.startswith("41") for c in gg)
