"""Fetch a single-shot / reference source into the raw lake.

Replaces fetch_applyhome / fetch_competition / fetch_schools / fetch_schoolinfo /
fetch_gonggo. Each source lands its own data/raw/<subdir>/ table and prints a
short, source-specific summary. (The 공고문 launch universe now lives in
extract.gonggo.list_launches, so this file stays a thin runner.)

Usage:
    uv run python data_pipeline/scripts/fetch.py --source applyhome
    uv run python data_pipeline/scripts/fetch.py --source competition
    uv run python data_pipeline/scripts/fetch.py --source schools
    uv run python data_pipeline/scripts/fetch.py --source schoolinfo
    uv run python data_pipeline/scripts/fetch.py --source gonggo [--limit N]
"""

from __future__ import annotations

import argparse


def _fetch_applyhome(_args: argparse.Namespace) -> None:
    from data_pipeline.ingestion.applyhome import extract

    df = extract()
    if df.empty:
        print("applyhome: no rows landed")
        return
    print(f"applyhome: {len(df):,} 주택형 rows across {df['pblanc_no'].nunique():,} 공고")
    yrs = df["notice_date"].astype(str).str[:4].value_counts().sort_index()
    print("공고 year dist:", dict(yrs))
    ppm = df["supply_price_manwon"] / df["exclusive_area_m2"]
    print(
        "분양가 만원/㎡ (min/median/max):",
        round(ppm.min(), 1),
        round(ppm.median(), 1),
        round(ppm.max(), 1),
    )


def _fetch_competition(_args: argparse.Namespace) -> None:
    from data_pipeline.ingestion.applyhome import extract_competition

    df = extract_competition()
    if df.empty:
        print("competition: no rows landed")
        return
    print(f"competition: {len(df):,} rows across {df['PBLANC_NO'].nunique():,} 공고")


def _fetch_schools(_args: argparse.Namespace) -> None:
    from data_pipeline.ingestion.neis import extract

    df = extract()
    print(f"landed {len(df)} schools -> data/raw/schools/data.parquet")
    if df.empty:
        return
    print("\nby school_type:")
    print(df["school_type"].value_counts().to_string())
    print("\nby sido:")
    print(df["sido"].value_counts().to_string())
    print("\nrows missing road_address (should be 0):", int(df["road_address"].isna().sum()))


def _fetch_schoolinfo(_args: argparse.Namespace) -> None:
    from data_pipeline.ingestion.schoolinfo import extract

    df = extract()
    if df.empty:
        print("schoolinfo: no rows landed")
        return
    print(f"schoolinfo: {len(df):,} HS rows across {df['sigungu_code'].nunique()} 시군구")
    print("HS type counts:")
    print(df["hs_type"].value_counts().to_string())
    gr = df["grad_rate"].dropna()
    print(f"진학률 %: min {gr.min():.1f} / median {gr.median():.1f} / max {gr.max():.1f}")


def _fetch_gonggo(args: argparse.Namespace) -> None:
    from data_pipeline.ingestion import gonggo

    launches = gonggo.list_launches(limit=args.limit)
    print(f"launches to fetch (2024+): {len(launches)}")
    out = gonggo.extract(launches)
    n_ceiling = int(out["price_ceiling"].sum()) if not out.empty and "price_ceiling" in out else 0
    print(
        f"parsed {len(out)} regulatory rows "
        f"({len(out) / max(len(launches), 1):.0%} of launches; {n_ceiling} 분양가상한제 적용)"
    )


SOURCES = {
    "applyhome": _fetch_applyhome,
    "competition": _fetch_competition,
    "schools": _fetch_schools,
    "schoolinfo": _fetch_schoolinfo,
    "gonggo": _fetch_gonggo,
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--source", required=True, choices=sorted(SOURCES))
    ap.add_argument("--limit", type=int, default=None, help="cap launches (gonggo only, testing)")
    args = ap.parse_args()
    SOURCES[args.source](args)


if __name__ == "__main__":
    main()
