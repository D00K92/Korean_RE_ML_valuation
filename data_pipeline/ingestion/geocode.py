"""Geocoding clients + persistent cache (VWorld getCoord, Kakao keyword search).

Turns an address / complex-name into (lat, lon). Two providers, each a thin,
retrying HTTP wrapper with NO business logic (the cascade that decides which
provider a row needs lives in features/geocoding.py):

  * VWorld getCoord  — PARCEL (지번) or ROAD (도로명) address -> coords.
  * Kakao keyword    — free-text place/complex name -> coords (block-code rows
                       whose jibun is an un-geocodable 블록 label, e.g. 'BL-3').

Every lookup goes through GeocodeCache: a query is hit at most once, ever —
NOT_FOUND is cached too, so misses are never re-billed. The cache is a single
Parquet file, write-through every `flush_every` new lookups, so a run that stops
on a daily quota resumes losslessly (same pattern as the ingest manifests).

Secrets: keys are read via get_settings().secrets and passed to the request;
they are NEVER logged, printed, or put in an exception message (CLAUDE.md).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from data_pipeline.config import get_settings

# cache methods (also the VWorld `type` values for the two address kinds)
PARCEL = "vworld_parcel"
ROAD = "vworld_road"
KEYWORD = "kakao_keyword"

_STATUS_OK = "OK"
_STATUS_MISS = "NOT_FOUND"


@dataclass(frozen=True)
class Coord:
    lat: float
    lon: float


# ---------------------------------------------------------------------------
# HTTP clients — raw calls only, no caching/cascade logic
# ---------------------------------------------------------------------------
class GeocodeClient:
    """Thin retrying wrapper over VWorld getCoord + Kakao keyword search."""

    def __init__(self) -> None:
        s = get_settings()
        self._gc = s.get("sources", "geocode", default={}) or {}
        self._vworld_url = self._gc.get("base_url", "https://api.vworld.kr/req/address")
        self._req = dict(self._gc.get("request_params", {}) or {})
        kk = self._gc.get("kakao_fallback", {}) or {}
        self._kakao_url = kk.get(
            "keyword_url", "https://dapi.kakao.com/v2/local/search/keyword.json"
        )
        self._vworld_search_url = self._gc.get("search_url", "https://api.vworld.kr/req/search")
        self._vworld_key = s.secrets.vworld_api_key
        self._kakao_key = s.secrets.kakao_rest_api_key
        # keyword tier: prefer Kakao (best recall); else fall back to VWorld place search
        self._kw_provider = "kakao" if self._kakao_key else ("vworld" if self._vworld_key else None)
        self.keyword_available = self._kw_provider is not None
        # pace requests — VWorld drops bursts (RemoteProtocolError) if hammered
        qps = float(self._gc.get("rate_limit_qps", 5) or 5)
        self._interval = 1.0 / qps if qps > 0 else 0.0
        self._last = 0.0
        self._client = httpx.Client(timeout=20)

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        if self._interval:
            wait = self._interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
        self._last = time.monotonic()

    # -- VWorld: 지번(PARCEL) / 도로명(ROAD) address -> coords --
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, max=60), reraise=True)
    def _vworld(self, address: str, addr_type: str) -> Coord | None:
        if not self._vworld_key:
            raise RuntimeError("VWORLD_API_KEY is not set.")
        params = {**self._req, "address": address, "type": addr_type, "key": self._vworld_key}
        self._throttle()
        r = self._client.get(self._vworld_url, params=params)
        if not r.is_success:  # NEVER surface the URL/status obj — it carries the key
            raise RuntimeError(f"VWorld HTTP {r.status_code}")
        resp = (r.json() or {}).get("response", {})
        status = resp.get("status")
        if status == "NOT_FOUND":
            return None
        if status != _STATUS_OK:
            # ERROR is usually a malformed address, not transient -> treat as miss
            return None
        point = (resp.get("result") or {}).get("point") or {}
        try:
            return Coord(lat=float(point["y"]), lon=float(point["x"]))
        except (KeyError, TypeError, ValueError):
            return None

    def geocode_parcel(self, address: str) -> Coord | None:
        return self._vworld(address, "PARCEL")

    def geocode_road(self, address: str) -> Coord | None:
        return self._vworld(address, "ROAD")

    # -- keyword tier: free-text complex/place name -> coords (Kakao or VWorld) --
    def search_keyword(self, query: str) -> Coord | None:
        if self._kw_provider == "kakao":
            return self._kakao_search(query)
        if self._kw_provider == "vworld":
            return self._vworld_search(query)
        raise RuntimeError("no keyword provider (set KAKAO_REST_API_KEY or VWORLD_API_KEY)")

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, max=60), reraise=True)
    def _kakao_search(self, query: str) -> Coord | None:
        headers = {"Authorization": f"KakaoAK {self._kakao_key}"}
        self._throttle()
        r = self._client.get(self._kakao_url, params={"query": query, "size": 1}, headers=headers)
        if not r.is_success:  # key travels in the header, but stay symmetric + quiet
            raise RuntimeError(f"Kakao HTTP {r.status_code}")
        docs = (r.json() or {}).get("documents") or []
        if not docs:
            return None
        try:
            return Coord(lat=float(docs[0]["y"]), lon=float(docs[0]["x"]))
        except (KeyError, TypeError, ValueError):
            return None

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, max=60), reraise=True)
    def _vworld_search(self, query: str) -> Coord | None:
        """VWorld place (POI) search — resolves complex names to an in-complex point."""
        params = {
            "service": "search",
            "request": "search",
            "version": "2.0",
            "crs": "EPSG:4326",
            "size": 5,
            "page": 1,
            "query": query,
            "type": "place",
            "format": "json",
            "key": self._vworld_key,
        }
        self._throttle()
        r = self._client.get(self._vworld_search_url, params=params)
        if not r.is_success:  # never surface the URL (carries the key)
            raise RuntimeError(f"VWorld search HTTP {r.status_code}")
        resp = (r.json() or {}).get("response", {})
        if resp.get("status") != _STATUS_OK:
            return None
        items = (resp.get("result") or {}).get("items") or []
        if not items:
            return None
        try:
            pt = items[0]["point"]
            return Coord(lat=float(pt["y"]), lon=float(pt["x"]))
        except (KeyError, TypeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# Persistent write-through cache: (method, query) -> coord | NOT_FOUND
# ---------------------------------------------------------------------------
class GeocodeCache:
    """A query is looked up at most once ever; misses are cached too.

    Backed by one Parquet file, flushed every `flush_every` new entries so a
    quota-interrupted run resumes without re-billing anything already resolved.
    """

    _COLS = ("method", "query", "status", "lat", "lon")

    def __init__(self, path: str | Path | None = None, flush_every: int | None = None) -> None:
        s = get_settings()
        gc = s.get("sources", "geocode", default={}) or {}
        self.path = Path(path or gc.get("cache_file", "data/processed/geocode/cache.parquet"))
        default_flush = gc.get("flush_every", 200)
        self.flush_every = int(flush_every if flush_every is not None else default_flush)
        self._mem: dict[tuple[str, str], dict[str, Any]] = {}
        self._dirty = 0
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            df = pd.read_parquet(self.path)
            for row in df.itertuples(index=False):
                self._mem[(row.method, row.query)] = {
                    "status": row.status,
                    "lat": row.lat,
                    "lon": row.lon,
                }

    def __len__(self) -> int:
        return len(self._mem)

    def get(self, method: str, query: str) -> tuple[bool, Coord | None] | None:
        """Return (hit_in_cache, coord). coord is None for a cached miss.

        Returns None when the query has never been looked up (caller must fetch).
        """
        rec = self._mem.get((method, query))
        if rec is None:
            return None
        if rec["status"] != _STATUS_OK:
            return (True, None)
        return (True, Coord(lat=rec["lat"], lon=rec["lon"]))

    def put(self, method: str, query: str, coord: Coord | None) -> None:
        self._mem[(method, query)] = (
            {"status": _STATUS_OK, "lat": coord.lat, "lon": coord.lon}
            if coord
            else {"status": _STATUS_MISS, "lat": None, "lon": None}
        )
        self._dirty += 1
        if self._dirty >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if self._dirty == 0 and self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"method": m, "query": q, **rec} for (m, q), rec in self._mem.items()]
        pd.DataFrame(rows, columns=list(self._COLS)).to_parquet(self.path, index=False)
        self._dirty = 0
