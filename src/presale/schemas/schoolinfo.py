"""Pydantic schema for a 학교알리미 졸업생 진로현황 (apiType 51) high-school row.

Provides the 학군-quality signal: school TYPE (특목고/자사고 vs 일반고) and 진학률.
Coordinates are NOT here — they come from joining SCHUL_NM to the geocoded NEIS
schools (features/school_quality.py). See docs / config sources.schoolinfo.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class SchoolOutcomeRecord(BaseModel):
    school_code: str
    name: str
    hs_type: str | None = None       # HS_KND_SC_NM: 일반고/특수목적고/자율고/특성화고
    grad_rate: float | None = None   # YEAR_GRAD_RATE (진학률 %)
    emd_code: str | None = None      # ADRCD_CD (10-digit 법정동)
    sigungu_code: str                # 5-digit, from the fetch loop

    @field_validator("grad_rate", mode="before")
    @classmethod
    def _rate(cls, v: object) -> float | None:
        s = str(v).strip()
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    @field_validator("name", "school_code")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not str(v).strip():
            raise ValueError("empty required field")
        return str(v).strip()
