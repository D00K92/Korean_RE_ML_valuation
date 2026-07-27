"""Schema for MOLIT 분양권전매 실거래가 records (the training label source).

Raw API fields are Korean and strings (with comma-separated prices, EUC-KR
text). This model normalizes them to typed columns and derives `deal_date`.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator, model_validator


class MolitResaleRecord(BaseModel):
    """One 분양권 resale transaction."""

    region_code: str = Field(..., description="5-digit LAWD_CD (법정동)")
    dong: str | None = Field(None, description="법정동 name")
    complex_name: str | None = Field(None, description="단지명")
    exclusive_area_m2: float = Field(..., gt=0, description="전용면적 (㎡)")
    floor: int | None = None
    deal_year: int = Field(..., ge=2000, le=2100)
    deal_month: int = Field(..., ge=1, le=12)
    deal_day: int = Field(..., ge=1, le=31)
    price_krw: int = Field(..., gt=0, description="거래금액 (원)")

    @field_validator("price_krw", mode="before")
    @classmethod
    def _strip_price(cls, v: object) -> object:
        # MOLIT returns "12,345" (만원 units in some feeds) — normalize commas.
        if isinstance(v, str):
            return int(v.replace(",", "").strip())
        return v

    @property
    def deal_date(self) -> dt.date:
        return dt.date(self.deal_year, self.deal_month, self.deal_day)

    @property
    def price_per_m2(self) -> float:
        """Realized resale price per ㎡ — the model label."""
        return self.price_krw / self.exclusive_area_m2

    @model_validator(mode="after")
    def _valid_date(self) -> MolitResaleRecord:
        # Raises ValueError on impossible dates (e.g. Feb 30) so bad rows drop.
        _ = self.deal_date
        return self
