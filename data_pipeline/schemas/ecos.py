"""Schema for ECOS (Bank of Korea) monthly macro observations.

One record per (series, month). ECOS returns TIME as 'YYYYMM' and DATA_VALUE as
a string; this validates the month and coerces the value to float. Series are
later pivoted to one wide row per month for the macro feature table.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EcosObservation(BaseModel):
    """One monthly value of one ECOS series."""

    series: str = Field(..., description="internal series name, e.g. base_rate")
    deal_ym: str = Field(..., description="YYYYMM (from ECOS TIME)")
    value: float = Field(..., description="DATA_VALUE coerced to float")
    unit: str | None = Field(None, description="UNIT_NAME (연%, 십억원, ...)")

    @field_validator("deal_ym", mode="before")
    @classmethod
    def _valid_month(cls, v: object) -> str:
        s = str(v).strip()
        if len(s) != 6 or not s.isdigit() or not (1 <= int(s[4:]) <= 12):
            raise ValueError(f"bad ECOS month: {v!r}")
        return s

    @field_validator("value", mode="before")
    @classmethod
    def _to_float(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.replace(",", "").strip()
            if s == "":
                raise ValueError("empty DATA_VALUE")
            return float(s)
        return v
