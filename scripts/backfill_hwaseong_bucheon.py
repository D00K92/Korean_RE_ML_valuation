"""Label backfill for the 7 부천/화성 구-level codes that complete molit_resale.

부천 (41190) and 화성 (41590) return no MOLIT data under their merged codes;
their transactions live under 구-level codes. This fills those into the label
lake via an explicit region override (so only these 7 are fetched). Merges into
data/raw/molit_resale/ using the same manifest as the rest of the label lake.
"""

from __future__ import annotations

import time

import presale.extract.molit as M
from presale.config import get_settings

CODES = ["41192", "41194", "41196", "41591", "41593", "41595", "41597"]


def main() -> None:
    s = get_settings()
    s.yaml["region"]["lawd_codes"] = CODES  # explicit override wins over prefixes
    print(f"화성/부천 label backfill: {len(CODES)} 구-level codes -> {CODES}")
    t0 = time.time()
    df = M.extract(mode="backfill")
    print(f"\nfetched {len(df)} rows in {(time.time() - t0) / 60:.1f} min")
    if not df.empty:
        by = df.groupby("region").size()
        print("rows per code:", by.to_dict())
        print("right_type:", df["right_type"].value_counts().to_dict())
        print(f"span: {df['deal_date'].min()} .. {df['deal_date'].max()}")


if __name__ == "__main__":
    main()
