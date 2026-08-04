"""Fetch + parse 입주자모집공고문 regulatory facts for 2024+ in-scope launches.

Reads the landed 청약홈 분양정보 (data/raw/applyhome) for the PBLANC list, filters to
`min_year` and the configured regions, then downloads + parses each 공고문 PDF and lands
the regulatory table to data/raw/gonggo/. PDFs are disk-cached, so re-runs are cheap.

Usage:  uv run python scripts/fetch_gonggo.py [--limit N]
"""

from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from presale.config import get_settings
from presale.extract import applyhome, gonggo


def _launch_frame() -> pd.DataFrame:
    """Distinct 2024+ launches (pblanc_no, house_manage_no, notice_date, region).

    Prefer the landed applyhome parquet; if absent, pull the odcloud detail feed live.
    """
    s = get_settings()
    min_year = int(s.get("sources", "applyhome", "gonggo", "min_year", default=2024))
    raw = pathlib.Path(s.get("paths", "raw_dir", default="data/raw")) / "applyhome" / "data.parquet"

    if raw.exists():
        df = pd.read_parquet(raw)
        # applyhome parquet lacks house_manage_no; for these launches it equals pblanc_no
        df = df.rename(columns={"supply_region": "supply_region"})
        df["house_manage_no"] = df["pblanc_no"]
        keep = ["pblanc_no", "house_manage_no", "notice_date", "supply_region"]
        df = df[[c for c in keep if c in df.columns]].drop_duplicates("pblanc_no")
    else:
        rows = applyhome._pull_all(  # noqa: SLF001 — reuse the paged puller
            get_settings().get("sources", "applyhome", "operations", "apt_detail")
        )
        df = pd.DataFrame([
            {
                "pblanc_no": r["PBLANC_NO"],
                "house_manage_no": r.get("HOUSE_MANAGE_NO", r["PBLANC_NO"]),
                "notice_date": r.get("RCRIT_PBLANC_DE"),
                "supply_region": r.get("SUBSCRPT_AREA_CODE_NM"),
            }
            for r in rows
        ]).drop_duplicates("pblanc_no")

    df["_year"] = df["notice_date"].astype(str).str[:4]
    return df[df["_year"].ge(str(min_year))].drop(columns="_year").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap number of launches (testing)")
    args = ap.parse_args()

    launches = _launch_frame()
    if args.limit:
        launches = launches.head(args.limit)
    print(f"launches to fetch (2024+): {len(launches)}")

    out = gonggo.extract(launches)
    n_ceiling = int(out["price_ceiling"].sum()) if not out.empty and "price_ceiling" in out else 0
    print(f"parsed {len(out)} regulatory rows "
          f"({len(out) / max(len(launches), 1):.0%} of launches; {n_ceiling} 분양가상한제 적용)")


if __name__ == "__main__":
    main()
