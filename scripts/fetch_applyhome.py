"""Fetch 청약홈 분양정보 (수도권, 2020+) -> data/raw/applyhome/data.parquet."""

from __future__ import annotations

from presale.extract.applyhome import extract


def main() -> None:
    df = extract()
    if df.empty:
        print("applyhome: no rows landed")
        return
    print(f"applyhome: {len(df):,} 주택형 rows across {df['pblanc_no'].nunique():,} 공고")
    yrs = df["notice_date"].astype(str).str[:4].value_counts().sort_index()
    print("공고 year dist:", dict(yrs))
    print("분양가 만원/㎡ (min/median/max):",
          round((df["supply_price_manwon"] / df["exclusive_area_m2"]).min(), 1),
          round((df["supply_price_manwon"] / df["exclusive_area_m2"]).median(), 1),
          round((df["supply_price_manwon"] / df["exclusive_area_m2"]).max(), 1))


if __name__ == "__main__":
    main()
