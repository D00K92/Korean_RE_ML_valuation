"""Static reference tables — cloud-backed lookups (法定동 codes, transit coords).

The 법정동코드 전체자료 (nationwide legal-dong codes, ~46k rows down to 읍면동·리
level) and the transit station/stop coordinate tables are static *inputs* to
ingestion/features. Their source of truth lives in GCS
(`gs://<bucket>/reference/`); `refstore.reference_path` fetches + caches them
locally (there is no `data/` lake). Tests set `REFERENCE_DIR` to read fixtures
offline. `bigquery_io` can also push the legal-dong table to BigQuery as
`ref_legal_dong`. The in-process `LegalDongResolver` reads the txt directly.

The 10-digit 법정동코드 is hierarchical:
    11        시도            (code[:2])
    11110     시군구 = LAWD_CD (code[:5])
    1111010100  읍면동·리       (full 10 digits)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from data_pipeline.warehouse.refstore import cache_dir, reference_path

# reference file NAMES in the cloud store (gs://<bucket>/reference/<name>); resolved
# to a local cached path by refstore.reference_path (offline: REFERENCE_DIR override).
LEGAL_DONG_TXT_NAME = "legal_dong_codes.txt"
SUBWAY_STATIONS_NAME = "subway_stations.parquet"
BUS_STOPS_NAME = "bus_stops.parquet"
LEGAL_DONG_TABLE = "ref_legal_dong"  # BigQuery table name (see bigquery_io)


def load_subway_stations() -> pd.DataFrame:
    """Nationwide metro stations: station_name, line, lat, lon, transfer_gbn."""
    return pd.read_parquet(reference_path(SUBWAY_STATIONS_NAME))


def load_bus_stops() -> pd.DataFrame:
    """수도권+부산 bus stops: stop_name, lat, lon, city."""
    return pd.read_parquet(reference_path(BUS_STOPS_NAME))


def _level(code: str) -> str:
    if code[2:] == "0" * 8:
        return "시도"
    if code[5:] == "00000":
        return "시군구"
    return "읍면동"


def load_legal_dong_frame(txt_path: Path | None = None) -> pd.DataFrame:
    """Parse the tab-separated 법정동코드 txt into a typed frame with hierarchy cols."""
    if txt_path is None:
        txt_path = reference_path(LEGAL_DONG_TXT_NAME)
    df = pd.read_csv(
        txt_path,
        sep="\t",
        dtype=str,
        encoding="utf-8",
        keep_default_na=False,
    )
    df.columns = ["code", "name", "status"]
    df = df[df["code"].str.fullmatch(r"\d{10}")].copy()
    df["is_active"] = df["status"].str.strip().eq("존재")
    df["sido_code"] = df["code"].str[:2]
    df["sigungu_code"] = df["code"].str[:5]
    df["emd_code"] = df["code"].str[5:]
    df["level"] = df["code"].map(_level)
    df["name"] = df["name"].str.strip()
    return df[
        ["code", "name", "status", "is_active", "sido_code", "sigungu_code", "emd_code", "level"]
    ]


def build_legal_dong_table(txt_path: Path | None = None, out_path: Path | None = None) -> int:
    """(Re)build the cached `legal_dong.parquet` from the GCS-backed txt. Returns row count.

    Materializes the reference table into the local cache; `bigquery_io` can push
    it to BigQuery as `ref_legal_dong`.
    """
    if out_path is None:
        out_path = cache_dir() / "legal_dong.parquet"
    df = load_legal_dong_frame(txt_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return len(df)


# ---------------------------------------------------------------------------
# Legal-dong name resolver
#
# MOLIT rows carry a 시군구 CODE (sggCd, exact) but only a dong NAME (umdNm, no
# code). Dong names drift over time (면→읍→동, 리→동 reorganizations), so the
# name join is best-effort: it enriches a row with a 10-digit legal-dong code
# when it can, and returns None otherwise — callers fall back to 시군구. It is
# never a filter, never drops a row.
# ---------------------------------------------------------------------------

# trailing administrative-unit suffixes to strip when comparing name stems
_DONG_SUFFIXES = ("읍", "면", "동", "리", "가")


def normalize_dong_name(name: str) -> str:
    """Reduce a dong/ri name to a comparison stem.

    Takes the last whitespace token (so '모현읍 왕산리' -> '왕산리') and strips a
    single trailing 읍/면/동/리/가 (so '고산동' and '고산리' both -> '고산'). This
    makes reorganized names (면→동, 리→동) compare equal to the reference.
    """
    if not name:
        return ""
    token = name.strip().split()[-1]
    if len(token) > 1 and token[-1] in _DONG_SUFFIXES:
        return token[:-1]
    return token


class LegalDongResolver:
    """Resolves (sigungu_code, umdNm) -> 10-digit legal-dong code, null-safe.

    Layered match, most precise first: full local name, then last token, then
    suffix-stripped stem. A layer resolves only when it maps to a *unique* code
    (ambiguous stems fall through to None rather than guess).
    """

    def __init__(self, ref: pd.DataFrame | None = None) -> None:
        ref = load_legal_dong_frame() if ref is None else ref
        active = ref[ref["is_active"]]
        sgg_name = {
            r.sigungu_code: r.name for r in active[active["level"] == "시군구"].itertuples()
        }
        emd = active[active["level"] == "읍면동"]

        self._by_local: dict[tuple[str, str], set[str]] = {}
        self._by_token: dict[tuple[str, str], set[str]] = {}
        self._by_stem: dict[tuple[str, str], set[str]] = {}
        for r in emd.itertuples():
            sgg = r.sigungu_code
            prefix = sgg_name.get(sgg, "")
            local = (
                r.name[len(prefix) :].strip() if prefix and r.name.startswith(prefix) else r.name
            )
            token = local.split()[-1] if local else ""
            self._by_local.setdefault((sgg, local), set()).add(r.code)
            self._by_token.setdefault((sgg, token), set()).add(r.code)
            self._by_stem.setdefault((sgg, normalize_dong_name(local)), set()).add(r.code)

    def resolve(self, sigungu_code: str, umd_name: str | None) -> str | None:
        if not umd_name:
            return None
        umd = umd_name.strip()
        for table, key in (
            (self._by_local, umd),
            (self._by_token, umd.split()[-1] if umd else ""),
            (self._by_stem, normalize_dong_name(umd)),
        ):
            hit = table.get((sigungu_code, key))
            if hit and len(hit) == 1:
                return next(iter(hit))
        return None

    def resolve_frame(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of legal-dong codes for a frame with region_code + dong."""
        return df.apply(lambda row: self.resolve(str(row["region_code"]), row.get("dong")), axis=1)
