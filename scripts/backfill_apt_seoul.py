"""Seoul apartment-trade (comp source) RAW backfill — all 25 Seoul 시군구.

Lands raw (untransformed) to data/raw/molit_apt_trade/. High volume + own
manifest, so this is resumable: if the daily quota is hit it stops cleanly and
rerunning continues where it left off (rolls over to the next day's quota).
Preprocessing is applied separately by scripts/preprocess_apt.py.
"""

from __future__ import annotations

import time

import presale.extract.molit_apt as A
from presale.config import get_settings


def main() -> None:
    seoul = [c for c in get_settings().resolve_lawd_codes() if c.startswith("11")]
    print(f"Seoul apt-trade RAW backfill: {len(seoul)} 시군구 (manifest skips already-landed)")
    t0 = time.time()
    df = A.extract(regions=seoul, mode="backfill")
    print(f"\nfetched {len(df)} raw rows this run in {(time.time() - t0) / 60:.1f} min")
    man = A.load_manifest()
    print(f"apt manifest: {len(man)} region-months across {man['region'].nunique()} regions")


if __name__ == "__main__":
    main()
