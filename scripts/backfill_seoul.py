"""One-off runner: MOLIT backfill for Seoul only (시도 prefix 11).

Overrides region selection in-process so config/settings.yaml stays at the full
Seoul+Gyeonggi scope for the eventual full run. Prints a per-region progress line
and a final summary. Uses the manifest + trailing-refresh logic in extract().
"""

from __future__ import annotations

import time

import presale.extract.molit as M
from presale.config import get_settings


def main() -> None:
    s = get_settings()
    seoul = [c for c in s.resolve_lawd_codes() if c.startswith("11")]
    s.yaml["region"]["lawd_codes"] = seoul  # in-memory override, file untouched

    print(f"Seoul backfill: {len(seoul)} 시군구, start_ym={s.get('ingest', 'start_ym')}")
    t0 = time.time()
    df = M.extract(mode="backfill")
    dt = time.time() - t0

    man = M.load_manifest()
    print("\n=== DONE ===")
    print(f"elapsed: {dt / 60:.1f} min")
    print(f"api calls (manifest rows): {len(man)}")
    print(f"non-empty region-months  : {int((man['n_rows'] > 0).sum())}")
    print(f"total label rows landed   : {len(df)}")
    if not df.empty:
        by = df.groupby("region").size().sort_values(ascending=False)
        print(f"regions with data: {by.size}/{len(seoul)}")
        print("top 5 regions by rows:", by.head(5).to_dict())
        print(f"date span: {df['deal_date'].min()} .. {df['deal_date'].max()}")


if __name__ == "__main__":
    main()
