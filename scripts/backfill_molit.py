"""MOLIT backfill over the FULL configured region scope (config/settings.yaml).

Unlike backfill_seoul.py (which pins Seoul), this runs whatever
region.resolve_lawd_codes() yields — currently 수도권 core (Seoul + Gyeonggi
minus far exurbs). The fetch manifest skips region-months already landed, so
re-running after a Seoul-only backfill only pulls the new Gyeonggi codes.
"""

from __future__ import annotations

import time

import presale.extract.molit as M
from presale.config import get_settings


def main() -> None:
    s = get_settings()
    codes = s.resolve_lawd_codes()
    seoul = sum(c.startswith("11") for c in codes)
    gg = sum(c.startswith("41") for c in codes)
    print(f"MOLIT backfill scope: {len(codes)} 시군구 (Seoul {seoul} + Gyeonggi {gg})")
    print(f"start_ym={s.get('ingest', 'start_ym')}  (manifest skips already-landed months)")

    t0 = time.time()
    df = M.extract(mode="backfill")
    dt = time.time() - t0

    man = M.load_manifest()
    print("\n=== DONE ===")
    print(f"elapsed: {dt / 60:.1f} min")
    print(f"manifest rows (all-time): {len(man)}")
    print(f"rows fetched THIS run    : {len(df)}")
    if not df.empty:
        by = df.groupby("region").size().sort_values(ascending=False)
        print(f"regions touched this run: {by.size}")
        print("top 5:", by.head(5).to_dict())
        print(f"date span this run: {df['deal_date'].min()} .. {df['deal_date'].max()}")


if __name__ == "__main__":
    main()
