"""Schema for NEIS 학교기본정보 records (school amenity reference).

One record per school. NEIS gives 도로명주소 but no coordinates, so `road_address`
is retained for later geocoding (VWorld ROAD). `school_type` (초/중/고) is the key
feature dimension. Records without a road address are dropped (can't be geocoded).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SchoolRecord(BaseModel):
    """One school from NEIS schoolInfo."""

    school_code: str = Field(..., description="SD_SCHUL_CODE (표준학교코드)")
    name: str = Field(..., description="SCHUL_NM")
    school_type: str = Field(..., description="SCHUL_KND_SC_NM: 초등학교/중학교/고등학교/...")
    foundation: str | None = Field(None, description="FOND_SC_NM: 공립/사립")
    office: str | None = Field(None, description="ATPT_OFCDC_SC_NM (교육청)")
    sido: str | None = Field(None, description="LCTN_SC_NM (시도)")
    road_address: str = Field(..., description="ORG_RDNMA (도로명주소) — geocoded later")
    road_address_detail: str | None = Field(None, description="ORG_RDNDA")
    coedu: str | None = Field(None, description="COEDU_SC_NM (남/여/공학)")

    @field_validator("road_address", "name", "school_code", mode="before")
    @classmethod
    def _require_nonempty(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("required school field is empty")
        return v.strip() if isinstance(v, str) else v
