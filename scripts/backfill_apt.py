"""Apartment-trade (comp source) RAW backfill over the FULL configured scope.

Runs region.resolve_lawd_codes() — currently 63 수도권-core 시군구 (incl. the
부천/화성 구-level codes) — so the comp coverage matches the molit_resale label
lake. The apt manifest skips region-months already landed (e.g. the 25 Seoul gu),
so this effectively fetches the Gyeonggi codes. Rollover-safe: if the daily quota
is hit it stops cleanly and rerunning resumes.
"""

from __future__ import annotations

import time

import presale.extract.molit_apt as A
from presale.config import get_settings


def main() -> None:
    codes = get_settings().resolve_lawd_codes()
    seoul = sum(c.startswith("11") for c in codes)
    gg = sum(c.startswith("41") for c in codes)
    print(f"apt-trade RAW backfill scope: {len(codes)} 시군구 (Seoul {seoul} + Gyeonggi {gg})")
    print("manifest skips already-landed region-months (Seoul already done)")
    t0 = time.time()
    df = A.extract(regions=codes, mode="backfill")
    print(f"\nfetched {len(df)} raw rows this run in {(time.time() - t0) / 60:.1f} min")
    man = A.load_manifest()
    print(f"apt manifest now: {len(man)} region-months across {man['region'].nunique()} regions")


if __name__ == "__main__":
    main()
