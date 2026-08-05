"""Schema for MOLIT 분양권·입주권 전매 실거래가 records (the training label source).

Raw API fields are English-keyed strings (comma-separated prices, EUC-KR text).
This model normalizes them to typed columns and derives `deal_date`. Two
domain conventions (owner decision, 2026-07-28):
  - prices are kept in **만원 (10,000 KRW)** — the Korean property-sector standard
    — NOT converted to won. `price_manwon` and `price_per_m2` are both in 만원.
  - `exclusive_area_m2` (전용면적) is floored to 2 decimal places.
`ownershipGbn` ('입'=입주권, empty=분양권) is kept as `right_type`.
"""

from __future__ import annotations

import datetime as dt
import math

from pydantic import BaseModel, Field, field_validator, model_validator


class MolitResaleRecord(BaseModel):
    """One 분양권 or 입주권 resale (전매) transaction."""

    region_code: str = Field(..., description="5-digit LAWD_CD (시군구)")
    dong: str | None = Field(None, description="법정동 (umdNm)")
    jibun: str | None = Field(None, description="지번")
    complex_name: str | None = Field(None, description="단지명 (aptNm)")
    exclusive_area_m2: float = Field(..., gt=0, description="전용면적 ㎡ (excluUseAr), floored 2dp")
    floor: int | None = None
    deal_year: int = Field(..., ge=2000, le=2100)
    deal_month: int = Field(..., ge=1, le=12)
    deal_day: int = Field(..., ge=1, le=31)
    price_manwon: int = Field(..., gt=0, description="거래금액 만원 (dealAmount, sector std)")
    right_type: str = Field("분양권", description="ownershipGbn: '입'→입주권 else 분양권")
    deal_channel: str | None = Field(None, description="중개거래 / 직거래 (dealingGbn)")
    is_cancelled: bool = Field(False, description="cdealType set → 해제 거래 (excluded from label)")

    @field_validator("exclusive_area_m2", mode="before")
    @classmethod
    def _floor_area_2dp(cls, v: object) -> object:
        # 전용면적 comes as e.g. "112.8548"; floor DOWN to 2 d.p. -> 112.85.
        if v is None or v == "":
            return v
        return math.floor(float(v) * 100) / 100

    @field_validator("price_manwon", mode="before")
    @classmethod
    def _strip_price(cls, v: object) -> object:
        # dealAmount is already in 만원, e.g. "388,232". Strip thousands commas only.
        if isinstance(v, str):
            return int(v.replace(",", "").strip())
        return v

    @field_validator("right_type", mode="before")
    @classmethod
    def _map_right_type(cls, v: object) -> str:
        # ownershipGbn: '입' = 입주권; empty/None/other = 분양권.
        return "입주권" if isinstance(v, str) and v.strip() == "입" else "분양권"

    @property
    def deal_date(self) -> dt.date:
        return dt.date(self.deal_year, self.deal_month, self.deal_day)

    @property
    def price_per_m2(self) -> float:
        """Realized resale price per ㎡ in 만원 (from floored area) — the model label."""
        return self.price_manwon / self.exclusive_area_m2

    @model_validator(mode="after")
    def _valid_date(self) -> MolitResaleRecord:
        # Raises ValueError on impossible dates (e.g. Feb 30) so bad rows drop.
        _ = self.deal_date
        return self
