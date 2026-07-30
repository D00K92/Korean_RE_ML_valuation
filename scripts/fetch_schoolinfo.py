"""Fetch 학교알리미 HS 졸업생 진로현황 -> data/raw/schoolinfo/data.parquet."""

from __future__ import annotations

from presale.extract.schoolinfo import extract


def main() -> None:
    df = extract()
    if df.empty:
        print("schoolinfo: no rows landed")
        return
    print(f"schoolinfo: {len(df):,} HS rows across {df['sigungu_code'].nunique()} 시군구")
    print("HS type counts:")
    print(df["hs_type"].value_counts().to_string())
    gr = df["grad_rate"].dropna()
    print(f"진학률 %: min {gr.min():.1f} / median {gr.median():.1f} / max {gr.max():.1f}")


if __name__ == "__main__":
    main()
