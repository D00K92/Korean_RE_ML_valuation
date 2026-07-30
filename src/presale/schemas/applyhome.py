"""Pydantic schema for a 청약홈 분양정보 row (announcement ⨝ 주택형).

One row per (announcement, 주택형). 분양가 (LTTOT_TOP_AMOUNT) is already in 만원,
matching the sector unit used for the MOLIT label. 전용면적 is parsed from the
leading number of HOUSE_TY (e.g. '055.9200A' -> 55.92) and floored to 2 d.p. to
match the label's exclusive_area convention — NOT taken from SUPLY_AR, which is
공급면적. See CLAUDE.md invariant #3 (rev 2026-07-29): only launch-time fields.
"""

from __future__ import annotations

import math
import re
from datetime import date

from pydantic import BaseModel, field_validator

_LEAD_NUM = re.compile(r"[\d.]+")


class ApplyhomeRecord(BaseModel):
    pblanc_no: str
    house_name: str
    house_kind: str | None = None       # HOUSE_SECD_NM (APT 등)
    supply_region: str | None = None    # 서울 / 경기 / 인천
    address: str | None = None          # HSSPLY_ADRES (geocodable)
    notice_date: date                   # 공고일 — leakage guard basis
    move_in_ym: str | None = None       # 입주예정월 'YYYYMM'
    total_units: int | None = None
    builder: str | None = None          # 건설사 -> brand
    house_type: str                     # raw HOUSE_TY
    exclusive_area_m2: float            # parsed from house_type, floored 2 d.p.
    supply_price_manwon: int            # 분양가 (만원)

    @field_validator("exclusive_area_m2", mode="before")
    @classmethod
    def _area_from_house_type(cls, v: object) -> float:
        # accepts either a raw HOUSE_TY string or an already-parsed number
        m = _LEAD_NUM.match(str(v).strip())
        if not m:
            raise ValueError(f"cannot parse 전용면적 from HOUSE_TY={v!r}")
        return math.floor(float(m.group()) * 100) / 100  # floor, matches MOLIT

    @field_validator("supply_price_manwon", mode="before")
    @classmethod
    def _price_int(cls, v: object) -> int:
        return int(str(v).replace(",", "").strip())

    @field_validator("total_units", mode="before")
    @classmethod
    def _units_int(cls, v: object) -> int | None:
        s = str(v).replace(",", "").strip()
        return int(s) if s and s.lstrip("-").isdigit() else None
