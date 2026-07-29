"""Commercial (상가) RAW backfill over the full configured 수도권-core scope.

~1M rows across 63 시군구. Rollover-safe: stops cleanly on daily quota, resumes on
rerun. Preprocessing is applied separately by scripts/preprocess_commercial.py.
"""

from __future__ import annotations

import time

import presale.extract.commercial as C
from presale.config import get_settings


def main() -> None:
    codes = get_settings().resolve_lawd_codes()
    print(f"commercial RAW backfill: {len(codes)} 시군구 (manifest skips already-done)")
    t0 = time.time()
    df = C.extract(regions=codes)
    print(f"\nfetched {len(df)} raw rows this run in {(time.time() - t0) / 60:.1f} min")
    man = C.load_manifest()
    done, rows = man["region"].nunique(), int(man["n_rows"].sum())
    print(f"commercial manifest: {done} 시군구 done, {rows} rows total")


if __name__ == "__main__":
    main()
