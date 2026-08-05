"""Geocoding cascade: turn each property/amenity row into (lat, lon) + a
`geocode_precision` flag, using the cheapest source that works for that row.

Design (validated against the real lakes — see the address audit):

  schools     : ROAD(도로명주소)  ─► keyword(name)                       [road/keyword]
  apt-trade   : PARCEL(지번)      ─► keyword(aptNm)                      [parcel/keyword]
  label 분양권 : if jibun is a real parcel ─► PARCEL                      [parcel]
                if jibun is a BLOCK code ('BL-3', 'A2블록', ...):
                   ─► borrow coords from a same-복합 apt-trade row (free) [borrow]
                   ─► keyword(complex_name)                              [keyword]
                   ─► dong-centroid of already-resolved rows (flagged)  [centroid]

Only ~63% of label rows carry a parcel-geocodable jibun; the block-code 37% is
why the borrow/keyword/centroid cascade exists. Every returned row gets a
`geocode_precision` so downstream features (and the README's Known Limitations)
can weight or exclude the low-precision tail.
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from data_pipeline.ingestion.geocode import (
    KEYWORD,
    PARCEL,
    ROAD,
    Coord,
    GeocodeCache,
    GeocodeClient,
)
from data_pipeline.warehouse.reference import (
    LegalDongResolver,
    load_legal_dong_frame,
    normalize_dong_name,
)

# precision tiers, best -> worst
P_PARCEL = "parcel"
P_ROAD = "road"
P_KEYWORD = "keyword"
P_BORROW = "borrow"
P_CENTROID = "centroid"
P_NONE = "none"

_PARCEL_RE = re.compile(r"^(산\s*)?\d+(-\d+)?$")


# ---------------------------------------------------------------------------
# Name / address normalization
# ---------------------------------------------------------------------------
def is_block_code(jibun: str | None) -> bool:
    """True when `jibun` is NOT a parcel-geocodable 지번 (i.e. a 블록/획지 label)."""
    if jibun is None:
        return True
    return not _PARCEL_RE.match(str(jibun).strip())


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


def search_name(name: str | None) -> str:
    """A human-searchable name for Kakao keyword lookup: NFKC + drop parentheticals,
    but KEEP 단지/차 (they disambiguate), just tidy whitespace."""
    s = unicodedata.normalize("NFKC", str(name or ""))
    s = re.sub(r"\([^)]*\)", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parcel_address(emd_full: str, jibun: str) -> str:
    """Build a VWorld PARCEL query, e.g. '서울특별시 종로구 교남동 산 37-19'."""
    j = str(jibun).strip()
    if j.startswith("산"):
        j = "산 " + j[1:].strip()
    return f"{emd_full} {j}".strip()


# 부천/화성 keep MOLIT 구-level codes that the 법정동 table files under the parent
# city code (부천 abolished its 구 in 2016; 화성 became 특례시 in 2025). Dong-name
# resolution must fall back to the parent, or every parcel address fails to build.
_MERGED_PARENT = {
    "41192": "41190",
    "41194": "41190",
    "41196": "41190",  # 부천시
    "41591": "41590",
    "41593": "41590",
    "41595": "41590",
    "41597": "41590",  # 화성시
}


class AddressIndex:
    """법정동 name lookups: 시군구 code -> '시도 시군구', (sgg, dong) -> full 읍면동 name."""

    def __init__(self) -> None:
        ref = load_legal_dong_frame()
        active = ref[ref["is_active"]]
        self._sgg_name = {
            r.sigungu_code: r.name for r in active[active["level"] == "시군구"].itertuples()
        }
        self._code_name = dict(zip(active["code"], active["name"], strict=False))
        self._resolver = LegalDongResolver(ref)

    def sgg_name(self, sgg: str) -> str:
        sgg = str(sgg)
        name = self._sgg_name.get(sgg)
        if name is None and sgg in _MERGED_PARENT:  # 부천/화성 구-code -> parent city
            name = self._sgg_name.get(_MERGED_PARENT[sgg], "")
        return name or ""

    def emd_full_name(self, sgg: str, dong: str | None) -> str | None:
        sgg = str(sgg)
        code = self._resolver.resolve(sgg, dong)
        if code is None and sgg in _MERGED_PARENT:  # retry under parent city code
            code = self._resolver.resolve(_MERGED_PARENT[sgg], dong)
        return self._code_name.get(code) if code else None


# ---------------------------------------------------------------------------
# Cache-backed single-query resolution
# ---------------------------------------------------------------------------
def _resolve(client: GeocodeClient, cache: GeocodeCache, method: str, query: str) -> Coord | None:
    """Look a query up through the cache; fetch + cache on a miss. '' never fetched."""
    if not query:
        return None
    # keyword path needs a Kakao key; if unset, degrade to a miss WITHOUT caching
    # (so it retries automatically once the key is added) instead of crashing.
    if method == KEYWORD and not getattr(client, "keyword_available", True):
        return None
    cached = cache.get(method, query)
    if cached is not None:
        return cached[1]
    if method == PARCEL:
        coord = client.geocode_parcel(query)
    elif method == ROAD:
        coord = client.geocode_road(query)
    else:
        coord = client.search_keyword(query)
    cache.put(method, query, coord)
    return coord


# ---------------------------------------------------------------------------
# Per-source cascades
# ---------------------------------------------------------------------------
def geocode_schools(df: pd.DataFrame, client: GeocodeClient, cache: GeocodeCache) -> pd.DataFrame:
    """ROAD-geocode NEIS schools on `road_address`; keyword(name) as fallback."""
    out = df.copy()
    lats, lons, precs = [], [], []
    for row in out.itertuples(index=False):
        coord = _resolve(client, cache, ROAD, str(getattr(row, "road_address", "") or "").strip())
        prec = P_ROAD
        if coord is None:
            name = str(getattr(row, "name", "") or "")
            sido = str(getattr(row, "sido", "") or "")
            coord = _resolve(client, cache, KEYWORD, f"{sido} {name}".strip())
            prec = P_KEYWORD if coord else P_NONE
        lats.append(coord.lat if coord else None)
        lons.append(coord.lon if coord else None)
        precs.append(prec)
    out["lat"], out["lon"], out["geocode_precision"] = lats, lons, precs
    return out


def geocode_apt(
    df: pd.DataFrame, client: GeocodeClient, cache: GeocodeCache, index: AddressIndex | None = None
) -> pd.DataFrame:
    """PARCEL-geocode apt-trade on 지번 (sggCd+umdNm+jibun); keyword(aptNm) fallback.

    Deduped on the distinct (sgg, dong, jibun, aptNm) key so ~1.5M rows cost only
    a few hundred-K unique lookups; coords are then broadcast back to every row.
    """
    index = index or AddressIndex()
    out = df.copy()
    out["_sgg"] = out["sggCd"].astype(str).str[:5]
    keys = out[["_sgg", "umdNm", "jibun", "aptNm"]].drop_duplicates()

    resolved: dict[tuple, tuple[float | None, float | None, str]] = {}
    for sgg, dong, jibun, aptnm in keys.itertuples(index=False):
        coord, prec = None, P_NONE
        emd = index.emd_full_name(sgg, dong)
        if emd and not is_block_code(jibun):
            coord = _resolve(client, cache, PARCEL, _parcel_address(emd, jibun))
            prec = P_PARCEL if coord else P_NONE
        if coord is None:
            q = f"{index.sgg_name(sgg)} {search_name(aptnm)}".strip()
            coord = _resolve(client, cache, KEYWORD, q)
            prec = P_KEYWORD if coord else P_NONE
        resolved[(sgg, dong, jibun, aptnm)] = (
            coord.lat if coord else None,
            coord.lon if coord else None,
            prec,
        )

    trip = out.apply(lambda r: resolved[(r["_sgg"], r["umdNm"], r["jibun"], r["aptNm"])], axis=1)
    out["lat"] = [t[0] for t in trip]
    out["lon"] = [t[1] for t in trip]
    out["geocode_precision"] = [t[2] for t in trip]
    return out.drop(columns=["_sgg"])


def build_borrow_index(apt_geocoded: pd.DataFrame) -> dict[tuple[str, str], Coord]:
    """(base_name(aptNm), sgg) -> Coord, from successfully geocoded apt-trade rows.

    Used to hand a block-code label row the coordinates of the SAME complex found
    (with a real parcel) in the apt-trade lake — zero extra API calls.
    """
    idx: dict[tuple[str, str], Coord] = {}
    g = apt_geocoded.dropna(subset=["lat", "lon"])
    for row in g.itertuples(index=False):
        sgg = str(getattr(row, "sggCd", ""))[:5]
        key = (base_name(getattr(row, "aptNm", "")), sgg)
        if key[0] and key not in idx:
            idx[key] = Coord(lat=row.lat, lon=row.lon)
    return idx


def _centroids(resolved: pd.DataFrame) -> tuple[dict, dict]:
    """(sgg, dong_stem)->mean coord and sgg->mean coord, from already-resolved rows."""
    g = resolved.dropna(subset=["lat", "lon"]).copy()
    g["_sgg"] = g["region_code"].astype(str).str[:5]
    g["_stem"] = g["dong"].map(normalize_dong_name)
    dong_c = {
        k: Coord(lat=v.lat, lon=v.lon)
        for k, v in g.groupby(["_sgg", "_stem"])[["lat", "lon"]].mean().iterrows()
    }
    sgg_c = {
        k: Coord(lat=v.lat, lon=v.lon)
        for k, v in g.groupby("_sgg")[["lat", "lon"]].mean().iterrows()
    }
    return dong_c, sgg_c


def geocode_label(
    df: pd.DataFrame,
    client: GeocodeClient,
    cache: GeocodeCache,
    borrow_index: dict[tuple[str, str], Coord] | None = None,
    index: AddressIndex | None = None,
) -> pd.DataFrame:
    """Four-tier cascade for the 분양권 label. `borrow_index` from build_borrow_index."""
    index = index or AddressIndex()
    borrow_index = borrow_index or {}
    out = df.copy()
    out["sgg5"] = out["region_code"].astype(str).str[:5]

    lats: list[float | None] = []
    lons: list[float | None] = []
    precs: list[str] = []
    for row in out.itertuples(index=False):
        sgg = row.sgg5
        jibun = getattr(row, "jibun", None)
        dong = getattr(row, "dong", None)
        cname = getattr(row, "complex_name", None)
        coord, prec = None, P_NONE

        if not is_block_code(jibun):
            emd = index.emd_full_name(sgg, dong)
            if emd:
                coord = _resolve(client, cache, PARCEL, _parcel_address(emd, jibun))
                prec = P_PARCEL if coord else P_NONE

        if coord is None:  # block code, or parcel miss
            borrowed = borrow_index.get((base_name(cname), sgg))
            if borrowed is not None:
                coord, prec = borrowed, P_BORROW
        if coord is None:
            q = f"{index.sgg_name(sgg)} {search_name(cname)}".strip()
            coord = _resolve(client, cache, KEYWORD, q)
            prec = P_KEYWORD if coord else P_NONE

        lats.append(coord.lat if coord else None)
        lons.append(coord.lon if coord else None)
        precs.append(prec)

    out["lat"], out["lon"], out["geocode_precision"] = lats, lons, precs

    # dong-centroid fallback for whatever is still unresolved (flagged low-precision)
    unresolved = out["lat"].isna()
    if unresolved.any():
        dong_c, sgg_c = _centroids(out)
        for i in out.index[unresolved]:
            sgg = out.at[i, "sgg5"]
            stem = normalize_dong_name(out.at[i, "dong"])
            c = dong_c.get((sgg, stem)) or sgg_c.get(sgg)
            if c is not None:
                out.at[i, "lat"], out.at[i, "lon"] = c.lat, c.lon
                out.at[i, "geocode_precision"] = P_CENTROID
    return out.drop(columns=["sgg5"])
