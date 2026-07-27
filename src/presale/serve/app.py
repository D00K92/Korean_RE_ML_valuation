"""Streamlit dashboard: score Applyhome upcoming launches, rank by estimated
premium (predicted resale/㎡ − base price/㎡), surface risk flags.

Run: streamlit run src/presale/serve/app.py
"""

from __future__ import annotations

import streamlit as st


def main() -> None:
    st.set_page_config(page_title="Presale Rights — Upcoming Launches", layout="wide")
    st.title("분양권 Resale-Price Predictions")
    st.caption(
        "Predicted realized resale price per ㎡ for upcoming launches "
        "(Seoul + Gyeonggi). Predictions call the FastAPI /predict endpoint."
    )
    st.info("Dashboard not yet implemented — see presale_pipeline_2week_scope.md, Day 12.")


if __name__ == "__main__":
    main()
