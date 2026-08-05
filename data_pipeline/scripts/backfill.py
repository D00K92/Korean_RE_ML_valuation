"""Historical RAW backfill for one source over a chosen region scope.

Replaces the per-source/per-region one-off runners (backfill_molit / _seoul /
_apt / _apt_seoul / _hwaseong_bucheon / _commercial / _ecos). Every extractor is
resumable via its own manifest, so a rerun skips already-landed region-months
(and rolls over cleanly when a daily API quota is hit).

Usage:
    uv run python data_pipeline/scripts/backfill.py --source molit  # full scope
    uv run python data_pipeline/scripts/backfill.py --source molit --region seoul
    uv run python data_pipeline/scripts/backfill.py --source molit --region hwaseong_bucheon
    uv run python data_pipeline/scripts/backfill.py --source apt --region 41,28  # prefixes
    uv run python data_pipeline/scripts/backfill.py --source commercial
    uv run python data_pipeline/scripts/backfill.py --source ecos  # region-agnostic
"""

from __future__ import annotations

import argparse
import time

import pandas as pd

from data_pipeline.config import get_settings


def _run_molit(codes: list[str]) -> pd.DataFrame:
    import data_pipeline.ingestion.molit as M

    get_settings().yaml["region"]["lawd_codes"] = codes  # in-memory override; file untouched
    return M.extract(mode="backfill")


def _run_apt(codes: list[str]) -> pd.DataFrame:
    import data_pipeline.ingestion.molit_apt as A

    return A.extract(regions=codes, mode="backfill")


def _run_commercial(codes: list[str]) -> pd.DataFrame:
    import data_pipeline.ingestion.commercial as C

    return C.extract(regions=codes)


def _run_ecos(_codes: list[str]) -> pd.DataFrame:
    from data_pipeline.ingestion.ecos import extract

    return extract()


# source -> (runner, region_aware)
SOURCES = {
    "molit": (_run_molit, True),
    "apt": (_run_apt, True),
    "commercial": (_run_commercial, True),
    "ecos": (_run_ecos, False),
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    ap.add_argument(
        "--region",
        default="all",
        help="all | seoul | gyeonggi | hwaseong_bucheon | comma-separated prefixes/codes",
    )
    args = ap.parse_args()

    run, region_aware = SOURCES[args.source]
    codes = get_settings().select_regions(args.region) if region_aware else []
    if region_aware:
        seoul = sum(c.startswith("11") for c in codes)
        gg = sum(c.startswith("41") for c in codes)
        print(
            f"{args.source} backfill: {len(codes)} 시군구 "
            f"(Seoul {seoul} + Gyeonggi {gg}), region={args.region!r}"
        )
    else:
        print(f"{args.source} backfill (region-agnostic)")

    t0 = time.time()
    df = run(codes)
    dt = (time.time() - t0) / 60
    n = 0 if df is None else len(df)
    print(f"\n=== DONE === fetched {n:,} rows this run in {dt:.1f} min")
    if df is not None and not df.empty:
        if "region" in df.columns:
            by = df.groupby("region").size().sort_values(ascending=False)
            print(f"regions touched: {by.size}; top 5: {by.head(5).to_dict()}")
        if "deal_date" in df.columns:
            print(f"date span: {df['deal_date'].min()} .. {df['deal_date'].max()}")


if __name__ == "__main__":
    main()
