"""Tests for the daily incremental refresh — ledger logic, no network.

The extractors are stubbed; we drive `refresh_feed`/`update_ledger` with crafted
frames to prove: first-seen stamping, idempotency, cancellation + 등기 transitions,
and outage safety (a 0-row day never corrupts the ledger).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from presale.extract import realtime


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path, monkeypatch):
    """Point the ledger/delta dirs at a temp location for each test."""
    settings = realtime.get_settings()
    orig = settings.get

    def fake_get(*keys, default=None):
        if keys == ("sources", "realtime", "ledger_dir"):
            return str(tmp_path / "ledger")
        if keys == ("sources", "realtime", "delta_dir"):
            return str(tmp_path / "deltas")
        return orig(*keys, default=default)

    monkeypatch.setattr(settings, "get", fake_get)


def _comps(rows):
    """Build a raw apt-trade frame (the shape _normalize_comps expects)."""
    return pd.DataFrame(
        [
            dict(region="11680", aptNm=a, jibun=j, excluUseAr=ar, floor=fl,
                 dealYear=2026, dealMonth=6, dealDay=d, dealAmount=amt,
                 cdealType=cx, rgstDate=rg)
            for (a, j, ar, fl, d, amt, cx, rg) in rows
        ]
    )


def test_first_seen_and_idempotency():
    obs = realtime._normalize_comps(_comps([
        ("자이", "100", 84.9, 5, 10, "120,000", "", ""),
        ("래미안", "200", 59.9, 3, 12, "90,000", "", ""),
    ]))
    d1 = realtime.update_ledger("comps", obs, date(2026, 7, 1))
    assert d1 == {"n_window": 2, "n_new": 2, "n_cancelled_new": 0, "n_rgst_new": 0}

    # same data next day -> nothing new (idempotent); first_seen preserved
    d2 = realtime.update_ledger("comps", obs, date(2026, 7, 2))
    assert d2["n_new"] == 0
    led = realtime.load_ledger("comps")
    assert len(led) == 2
    assert (led["first_seen_date"] == pd.Timestamp("2026-07-01")).all()
    assert (led["last_seen_date"] == pd.Timestamp("2026-07-02")).all()


def test_cancellation_and_rgst_transitions():
    active = realtime._normalize_comps(_comps([("자이", "100", 84.9, 5, 10, "120,000", "", "")]))
    cancelled = realtime._normalize_comps(
        _comps([("자이", "100", 84.9, 5, 10, "120,000", "O", "26.07.15")])
    )
    realtime.update_ledger("comps", active, date(2026, 7, 1))
    # next day the SAME deal shows 해제(cdealType) + an 등기일자
    d = realtime.update_ledger("comps", cancelled, date(2026, 7, 3))
    assert d["n_new"] == 0 and d["n_cancelled_new"] == 1 and d["n_rgst_new"] == 1
    led = realtime.load_ledger("comps").iloc[0]
    assert led["cancelled_date"] == pd.Timestamp("2026-07-03")
    assert led["rgst_filled_date"] == pd.Timestamp("2026-07-03")

    # a THIRD day still cancelled -> no double-count (transition stamped once)
    d3 = realtime.update_ledger("comps", cancelled, date(2026, 7, 4))
    assert d3["n_cancelled_new"] == 0


def test_outage_day_is_safe():
    realtime.update_ledger("comps",
        realtime._normalize_comps(_comps([("자이", "100", 84.9, 5, 10, "120,000", "", "")])),
        date(2026, 7, 1))
    # an API-outage day: 0 rows returned -> no updates, ledger untouched
    empty = realtime._normalize_comps(pd.DataFrame())
    d = realtime.update_ledger("comps", empty, date(2026, 7, 2))
    assert d == {"n_window": 0, "n_new": 0, "n_cancelled_new": 0, "n_rgst_new": 0}
    led = realtime.load_ledger("comps")
    assert len(led) == 1  # nothing marked cancelled by the outage
    assert pd.isna(led.iloc[0]["cancelled_date"])


def test_label_normalizer_and_refresh_feed(monkeypatch):
    label = pd.DataFrame([dict(
        region_code="36110", complex_name="세종자이", jibun="22-1",
        exclusive_area_m2=84.8, floor=7, deal_date="2026-06-16",
        price_manwon=60000, is_cancelled=False)])
    # stub the underlying extractor (FeedSpec is frozen, so patch what it calls)
    monkeypatch.setattr(realtime.molit, "extract", lambda mode="latest": label)
    out = realtime.refresh_feed("label", date(2026, 7, 5))
    assert out["feed"] == "label" and out["n_new"] == 1
    assert realtime.load_ledger("label").iloc[0]["region"] == "36110"
