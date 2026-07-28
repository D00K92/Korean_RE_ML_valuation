"""One-off runner: ECOS macro backfill (all configured monthly series).

~4 API calls total (one per series over the full span). Prints a summary of the
landed wide monthly table.
"""

from __future__ import annotations

from presale.extract.ecos import extract


def main() -> None:
    wide = extract()
    if wide.empty:
        print("ECOS: no data returned")
        return
    print(f"landed months: {len(wide)}  ({wide['deal_ym'].min()} .. {wide['deal_ym'].max()})")
    print(f"columns: {list(wide.columns)}")
    print("\nlatest 3 months:")
    print(wide.tail(3).to_string(index=False))
    print("\nnull counts:")
    print(wide.isna().sum().to_string())


if __name__ == "__main__":
    main()
