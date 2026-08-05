"""Manually run the daily incremental refresh (what the Airflow DAG calls).

Usage:
    uv run python data_pipeline/scripts/refresh.py                # all configured feeds
    uv run python data_pipeline/scripts/refresh.py --feeds comps  # one feed
"""

from __future__ import annotations

import argparse

from data_pipeline.ingestion.realtime import refresh


def main() -> None:
    parser = argparse.ArgumentParser(description="MOLIT 실거래가 daily incremental refresh")
    parser.add_argument("--feeds", nargs="*", help="subset of feeds (default: config)")
    args = parser.parse_args()
    for d in refresh(feeds=args.feeds):
        print(
            f"{d['feed']:6s} {d['run_date']}: window={d['n_window']:,} "
            f"new={d['n_new']:,} cancelled+={d['n_cancelled_new']} 등기+={d['n_rgst_new']}"
        )


if __name__ == "__main__":
    main()
