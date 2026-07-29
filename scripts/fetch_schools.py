"""Fetch NEIS schools for the configured offices (서울+경기) and land them.

~4k rows, static reference — cache-once. Prints a summary by school type and region.
"""

from __future__ import annotations

from presale.extract.neis import extract


def main() -> None:
    df = extract()
    print(f"landed {len(df)} schools -> data/raw/schools/data.parquet")
    if df.empty:
        return
    print("\nby school_type:")
    print(df["school_type"].value_counts().to_string())
    print("\nby sido:")
    print(df["sido"].value_counts().to_string())
    print("\nrows missing road_address (should be 0):", int(df["road_address"].isna().sum()))


if __name__ == "__main__":
    main()
