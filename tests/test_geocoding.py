"""Tests for the geocoding cascade + cache — no network (a fake client)."""

from __future__ import annotations

import pandas as pd
import pytest

from presale.extract.geocode import KEYWORD, PARCEL, ROAD, Coord, GeocodeCache
from presale.features.geocoding import (
    AddressIndex,
    base_name,
    build_borrow_index,
    geocode_label,
    geocode_schools,
    is_block_code,
    search_name,
)


class FakeClient:
    """Returns a Coord for queries present in `table[(method, query)]`, else None."""

    def __init__(self, table: dict[tuple[str, str], Coord]) -> None:
        self.table = table
        self.calls: list[tuple[str, str]] = []

    def geocode_parcel(self, q):  # noqa: D102
        self.calls.append((PARCEL, q))
        return self.table.get((PARCEL, q))

    def geocode_road(self, q):  # noqa: D102
        self.calls.append((ROAD, q))
        return self.table.get((ROAD, q))

    def search_keyword(self, q):  # noqa: D102
        self.calls.append((KEYWORD, q))
        return self.table.get((KEYWORD, q))


# -- normalization ----------------------------------------------------------
def test_is_block_code():
    assert is_block_code("BL-3") and is_block_code("A2블록") and is_block_code(None)
    assert not is_block_code("123") and not is_block_code("123-4") and not is_block_code("산37-19")


def test_base_name_strips_markers_and_fullwidth():
    assert base_name("경희궁자이(3BL)") == "경희궁자이"
    assert base_name("한강메트로자이2단지") == "한강메트로자이"
    # full-width digits/space must normalize so both sides match
    assert base_name("김포　풍무２차　푸르지오") == base_name("김포 풍무2차 푸르지오")


def test_search_name_keeps_danji_drops_paren():
    assert search_name("한강메트로자이2단지(A2)") == "한강메트로자이2단지"


# -- cache round-trip -------------------------------------------------------
def test_cache_roundtrip_and_miss(tmp_path):
    p = tmp_path / "cache.parquet"
    c = GeocodeCache(path=p, flush_every=1)
    assert c.get(ROAD, "x") is None  # never looked up
    c.put(ROAD, "x", Coord(37.5, 127.0))
    c.put(ROAD, "y", None)  # a cached MISS
    c2 = GeocodeCache(path=p)  # reload from disk
    hit, coord = c2.get(ROAD, "x")
    assert hit and coord.lat == 37.5
    hit, coord = c2.get(ROAD, "y")
    assert hit and coord is None  # miss is remembered, won't re-bill


# -- schools cascade --------------------------------------------------------
def test_schools_road_then_keyword(tmp_path):
    df = pd.DataFrame(
        {
            "name": ["가나초", "없는학교"],
            "sido": ["서울특별시", "서울특별시"],
            "road_address": ["서울특별시 종로구 사직로8길 4", "주소없음"],
        }
    )
    table = {
        (ROAD, "서울특별시 종로구 사직로8길 4"): Coord(37.57, 126.96),
        (KEYWORD, "서울특별시 없는학교"): Coord(37.5, 127.0),
    }
    out = geocode_schools(df, FakeClient(table), GeocodeCache(path=tmp_path / "c.parquet"))
    assert list(out["geocode_precision"]) == ["road", "keyword"]
    assert out["lat"].notna().all()


# -- label four-tier cascade ------------------------------------------------
def _label_index():
    return AddressIndex()


def test_label_parcel_path(tmp_path):
    idx = _label_index()
    emd = idx.emd_full_name("11110", "교남동")
    df = pd.DataFrame(
        {
            "region_code": ["11110"], "dong": ["교남동"],
            "jibun": ["30"], "complex_name": ["경희궁자이"],
        }
    )
    table = {(PARCEL, f"{emd} 30"): Coord(37.57, 126.96)}
    out = geocode_label(df, FakeClient(table), GeocodeCache(path=tmp_path / "c.parquet"), index=idx)
    assert out.loc[0, "geocode_precision"] == "parcel"


def test_label_block_borrow_beats_keyword(tmp_path):
    idx = _label_index()
    df = pd.DataFrame(
        {
            "region_code": ["11110"], "dong": ["교남동"],
            "jibun": ["BL-3"], "complex_name": ["경희궁자이(3BL)"],
        }
    )
    borrow = {("경희궁자이", "11110"): Coord(37.55, 126.97)}
    client = FakeClient({(KEYWORD, "서울특별시 종로구 경희궁자이"): Coord(1, 1)})
    out = geocode_label(df, client, GeocodeCache(path=tmp_path / "c.parquet"),
                        borrow_index=borrow, index=idx)
    assert out.loc[0, "geocode_precision"] == "borrow"
    assert out.loc[0, "lat"] == 37.55
    assert not client.calls  # borrow short-circuits BEFORE any keyword call


def test_label_block_keyword_then_centroid(tmp_path):
    idx = _label_index()
    # row A resolves via keyword; row B (same dong) has no source -> centroid of A
    df = pd.DataFrame(
        {
            "region_code": ["11110", "11110"],
            "dong": ["교남동", "교남동"],
            "jibun": ["BL-3", "BL-9"],
            "complex_name": ["있는단지", "유령단지"],
        }
    )
    table = {(KEYWORD, "서울특별시 종로구 있는단지"): Coord(37.60, 126.90)}
    out = geocode_label(df, FakeClient(table), GeocodeCache(path=tmp_path / "c.parquet"), index=idx)
    precs = dict(zip(out["complex_name"], out["geocode_precision"], strict=False))
    assert precs["있는단지"] == "keyword"
    assert precs["유령단지"] == "centroid"
    # centroid borrows the only resolved coord in the dong
    assert out.loc[out["complex_name"] == "유령단지", "lat"].iloc[0] == pytest.approx(37.60)


def test_build_borrow_index_uses_base_name():
    apt = pd.DataFrame(
        {"sggCd": ["11110"], "aptNm": ["경희궁자이(3단지)"], "lat": [37.5], "lon": [127.0]}
    )
    idx = build_borrow_index(apt)
    assert idx[("경희궁자이", "11110")].lat == 37.5
