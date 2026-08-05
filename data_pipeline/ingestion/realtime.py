"""Daily incremental refresh of the MOLIT 실거래가 lake (real-time freshness).

This is the *business logic* the daily Airflow DAG calls — importable, with **no
Airflow dependency** (per CLAUDE.md: DAGs orchestrate, they don't compute). See
docs/daily_incremental_job.md for the design.

What one daily run does, per feed (label 분양권 + comps 아파트매매):
  1. Re-fetch the trailing window via the existing incremental extractors
     (`molit.extract(mode="latest")` / `molit_apt.extract(mode="incremental")`).
     Those already replace the trailing months wholesale, so late reports, 해제
     (cancellations), and 등기 fills all reconcile automatically — idempotent.
  2. Update an append-only **first-seen ledger**: record the date each deal first
     became publicly visible (`first_seen_date`), plus when it was cancelled or
     got an 등기일자. This removes the flat "+30 day" reporting-lag approximation —
     training can filter comps by the *true* `first_seen_date` (invariant #1).
  3. Emit a small **delta audit** (new / cancelled / 등기 counts) for monitoring.

Outage safety: the ledger only ever *adds* information from rows that are present
in a fetch. A region returning 0 rows (e.g. the MOLIT 호남 gap) simply produces no
updates that day — it can never be misread as "everything cancelled".
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from data_pipeline.config import get_settings
from data_pipeline.ingestion import molit, molit_apt

# The common schema every feed is normalised to before it touches the ledger.
# One row = one transaction observed in this run.
_NORM_COLS = ["region", "deal_key", "deal_date", "is_cancelled", "has_rgst"]

# The ledger schema (append-only, one row per distinct deal ever seen).
_LEDGER_COLS = [
    "feed",
    "region",
    "deal_key",
    "first_seen_date",
    "last_seen_date",
    "cancelled_date",
    "rgst_filled_date",
]


def _deal_key(feed: str, region: str, *parts: object) -> str:
    """Stable content hash identifying one transaction across daily runs."""
    payload = "|".join([feed, str(region), *(str(p) for p in parts)])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]  # noqa: S324 (not security)


def _nonblank(series: pd.Series) -> pd.Series:
    """True where a raw MOLIT field is present (not None / '' / whitespace)."""
    return series.notna() & series.astype(str).str.strip().ne("")


# --------------------------------------------------------------------------- #
# Feed adapters: normalise each extractor's output to _NORM_COLS.
# Kept tiny and declarative so a new feed is one function + one FeedSpec entry.
# --------------------------------------------------------------------------- #
def _normalize_label(df: pd.DataFrame) -> pd.DataFrame:
    """분양권 (SilvTrade) processed rows -> common ledger schema."""
    if df.empty:
        return pd.DataFrame(columns=_NORM_COLS)
    out = pd.DataFrame()
    out["region"] = df["region_code"].astype(str)
    out["deal_key"] = [
        _deal_key(
            "label",
            r.region_code,
            r.complex_name,
            r.jibun,
            r.exclusive_area_m2,
            r.floor,
            r.deal_date,
            r.price_manwon,
        )
        for r in df.itertuples(index=False)
    ]
    out["deal_date"] = pd.to_datetime(df["deal_date"], errors="coerce")
    out["is_cancelled"] = df["is_cancelled"].astype(bool)
    out["has_rgst"] = False  # SilvTrade carries no 등기일자 field
    return out


def _normalize_comps(df: pd.DataFrame) -> pd.DataFrame:
    """아파트 매매 (AptTrade) raw rows -> common ledger schema."""
    if df.empty:
        return pd.DataFrame(columns=_NORM_COLS)
    out = pd.DataFrame()
    region = df["region"] if "region" in df else df["sggCd"]
    out["region"] = region.astype(str)
    out["deal_date"] = pd.to_datetime(
        dict(
            year=df["dealYear"].astype(int),
            month=df["dealMonth"].astype(int),
            day=df["dealDay"].astype(int),
        ),
        errors="coerce",
    )
    out["deal_key"] = [
        _deal_key("comps", reg, r.aptNm, r.jibun, r.excluUseAr, r.floor, dd, r.dealAmount)
        for reg, dd, r in zip(
            out["region"], out["deal_date"], df.itertuples(index=False), strict=False
        )
    ]
    out["is_cancelled"] = _nonblank(df["cdealType"]).to_numpy()  # 해제 거래
    out["has_rgst"] = _nonblank(df["rgstDate"]).to_numpy()  # 등기일자 filled
    return out


@dataclass(frozen=True)
class FeedSpec:
    """How to fetch + normalise one feed. Add a feed = add one entry."""

    fetch: Callable[[], pd.DataFrame]
    normalize: Callable[[pd.DataFrame], pd.DataFrame]


FEEDS: dict[str, FeedSpec] = {
    "label": FeedSpec(lambda: molit.extract(mode="latest"), _normalize_label),
    "comps": FeedSpec(lambda: molit_apt.extract(mode="incremental"), _normalize_comps),
}


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #
def _ledger_path(feed: str) -> Path:
    d = Path(
        get_settings().get("sources", "realtime", "ledger_dir", default="data/realtime/seen_ledger")
    )
    return d / f"{feed}.parquet"


def load_ledger(feed: str) -> pd.DataFrame:
    p = _ledger_path(feed)
    return pd.read_parquet(p) if p.exists() else pd.DataFrame(columns=_LEDGER_COLS)


def update_ledger(feed: str, observed: pd.DataFrame, run_date: date) -> dict[str, int]:
    """Merge this run's observed transactions into the feed's first-seen ledger.

    Rules (all monotonic — a fact, once recorded, is never unset):
      * unseen deal_key      -> append with first_seen_date = run_date
      * already-seen deal_key-> bump last_seen_date; stamp cancelled_date /
                                rgst_filled_date the first time each becomes true
    Returns the delta summary for the audit log.
    """
    ts = pd.Timestamp(run_date)
    ledger = load_ledger(feed)
    known = ledger.set_index("deal_key") if not ledger.empty else None

    seen = observed.drop_duplicates("deal_key")
    is_new = (
        ~seen["deal_key"].isin(ledger["deal_key"])
        if not ledger.empty
        else pd.Series(True, index=seen.index)
    )
    new_rows = seen[is_new]
    upd_rows = seen[~is_new]

    # 1) brand-new deals -> new ledger records. `_stamp` yields a datetime column =
    # run_date where the flag is True, else NaT (stays datetime64 even when empty).
    def _stamp(flag: pd.Series) -> pd.Series:
        out = pd.Series(pd.NaT, index=flag.index, dtype="datetime64[ns]")
        out[flag.to_numpy(dtype=bool)] = ts
        return out

    appended = pd.DataFrame(
        {
            "feed": feed,
            "region": new_rows["region"].to_numpy(),
            "deal_key": new_rows["deal_key"].to_numpy(),
            "first_seen_date": pd.Series(
                ts, index=new_rows.index, dtype="datetime64[ns]"
            ).to_numpy(),
            "last_seen_date": pd.Series(
                ts, index=new_rows.index, dtype="datetime64[ns]"
            ).to_numpy(),
            "cancelled_date": _stamp(new_rows["is_cancelled"]).to_numpy(),
            "rgst_filled_date": _stamp(new_rows["has_rgst"]).to_numpy(),
        }
    )

    n_cancelled_new = int(new_rows["is_cancelled"].sum())
    n_rgst_new = int(new_rows["has_rgst"].sum())

    # 2) previously-seen deals -> stamp last_seen + first-time cancel/등기 transitions
    if known is not None and not upd_rows.empty:
        for r in upd_rows.itertuples(index=False):
            row = known.loc[r.deal_key]
            known.at[r.deal_key, "last_seen_date"] = ts
            if r.is_cancelled and pd.isna(row["cancelled_date"]):
                known.at[r.deal_key, "cancelled_date"] = ts
                n_cancelled_new += 1
            if r.has_rgst and pd.isna(row["rgst_filled_date"]):
                known.at[r.deal_key, "rgst_filled_date"] = ts
                n_rgst_new += 1
        ledger = known.reset_index()

    merged = appended if ledger.empty else pd.concat([ledger, appended], ignore_index=True)
    p = _ledger_path(feed)
    p.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(p, index=False)

    return {
        "n_window": int(len(seen)),
        "n_new": int(len(new_rows)),
        "n_cancelled_new": n_cancelled_new,
        "n_rgst_new": n_rgst_new,
    }


# --------------------------------------------------------------------------- #
# Public API used by the DAG / CLI
# --------------------------------------------------------------------------- #
def refresh_feed(feed: str, run_date: date | None = None) -> dict:
    """Fetch one feed's trailing window, reconcile the lake, update the ledger.

    Returns a delta summary (JSON-serialisable) so an Airflow task can pass it
    downstream via XCom.
    """
    if feed not in FEEDS:
        raise ValueError(f"unknown feed {feed!r}; known: {list(FEEDS)}")
    run_date = run_date or date.today()
    spec = FEEDS[feed]
    fetched = spec.fetch()  # re-fetch + wholesale replace the trailing window
    observed = spec.normalize(fetched)  # -> common schema
    delta = update_ledger(feed, observed, run_date)
    return {"feed": feed, "run_date": run_date.isoformat(), **delta}


def write_audit(run_date: date, deltas: list[dict]) -> Path:
    """Persist the per-run delta summary (one row per feed) for monitoring."""
    delta_dir = Path(
        get_settings().get("sources", "realtime", "delta_dir", default="data/realtime/deltas")
    )
    delta_dir.mkdir(parents=True, exist_ok=True)
    path = delta_dir / f"{run_date.isoformat()}.parquet"
    pd.DataFrame(deltas).to_parquet(path, index=False)
    return path


def refresh(feeds: list[str] | None = None, run_date: date | None = None) -> list[dict]:
    """Convenience entrypoint (CLI / manual): refresh every feed + write the audit."""
    run_date = run_date or date.today()
    feeds = feeds or list(get_settings().get("sources", "realtime", "feeds", default=list(FEEDS)))
    deltas = [refresh_feed(f, run_date) for f in feeds]
    write_audit(run_date, deltas)
    return deltas
