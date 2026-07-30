"""Fetch 청약 경쟁률 (raw) -> data/raw/applyhome_competition/data.parquet."""

from __future__ import annotations

from presale.extract.applyhome import extract_competition


def main() -> None:
    df = extract_competition()
    if df.empty:
        print("competition: no rows landed")
        return
    print(f"competition: {len(df):,} rows across {df['PBLANC_NO'].nunique():,} 공고")


if __name__ == "__main__":
    main()
