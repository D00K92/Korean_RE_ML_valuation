"""Pydantic schema for regulatory facts parsed from a 입주자모집공고문 PDF.

The 청약홈 odcloud API exposes launch prices/units/dates but **not** the regulatory
regime (전매제한 / 분양가상한제 / 실거주의무 / 규제지역). That lives only in the
입주자모집공고문 PDF, in a compact summary box that is **format-consistent for 2024+
launches** (verified across a 40-doc sample; older docs scatter it in prose and are
out of scope). See docs/gonggo_pdf_extraction.md.

Every field here is **fixed at 공고 time**, so it is leakage-safe under CLAUDE.md
invariant #3: it may enrich a MOLIT resale row only when `공고일 <= deal_date`, the
same guard applied to the other 청약홈 launch-time fields in features/enrich.py.

Each field keeps a `_raw` (as-printed, auditable) form next to its parsed value.
The parser occasionally mis-anchors a table cell, so the `_raw` inputs are guarded
here: an implausible period (a boilerplate paragraph, or a value from the wrong
column such as '미적용') is dropped rather than mis-parsed. 규제지역/택지유형 free text
is collapsed to a clean categorical.

There is no API ground truth for these fields (unlike price, which cross-checks
against LTTOT_TOP_AMOUNT). Trust rests on (a) internal coherence — 분양가상한제 적용
implies a 실거주의무 and a longer 전매제한 — and (b) public 규제지역 고시 history.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator, model_validator

_YEARS = re.compile(r"(\d+)\s*년")
_MONTHS = re.compile(r"(\d+)\s*개\s*월")
# a genuine 전매/거주 value looks like a period ('없음', 'N년', 'N개월', or '…등기…');
# anything else (boilerplate prose, a stray '미적용' from the 상한제 column) is rejected.
_PERIOD_TOKEN = re.compile(r"(\d+\s*년|\d+\s*개\s*월|없음|등기)")
_BOILERPLATE = ("공통유의", "청약홈", "콜센터", "신청자격", "관한규칙", "관한 규칙")


def _to_months(raw: str | None) -> int | None:
    """'3년' -> 36, '6개월' -> 6, '없음' -> 0, unparseable -> None.

    Real 전매/거주 values seen: '없음', 'N개월', 'N년', and prose like
    '소유권이전등기일까지(다만, 3년을 초과하는 경우 3년)' — from which we take the year.
    """
    if not raw:
        return None
    if "없음" in raw or "해당없음" in raw or "해당 없음" in raw:
        return 0
    y = _YEARS.search(raw)
    m = _MONTHS.search(raw)
    total = (int(y.group(1)) * 12 if y else 0) + (int(m.group(1)) if m else 0)
    return total or None


def _clean_period(raw: str | None) -> str | None:
    """Drop mis-anchored 전매/거주 cell values; keep genuine period strings."""
    if not raw:
        return None
    s = str(raw).strip()
    if len(s) > 50 or any(k in s for k in _BOILERPLATE):
        return None                     # a paragraph, not a 전매/거주 period
    return s if _PERIOD_TOKEN.search(s) else None


def _normalize_zone(raw: str | None) -> str | None:
    """규제지역 free text -> {투기과열, 청약과열, 조정대상, 비규제}. Handles the many
    printed variants (spacing, '비-' negations, parentheticals) seen in the sample.
    """
    if not raw:
        return None
    s = re.sub(r"\s+", "", str(raw))
    if "비규제" in s or "비투기과열" in s:   # negated forms => not regulated
        return "비규제"
    if "조정대상" in s:
        return "조정대상"
    if "투기과열" in s:
        return "투기과열"
    if "청약과열" in s:
        return "청약과열"
    return None


def _normalize_land(raw: str | None) -> str | None:
    """택지유형 free text -> {민간택지, 공공택지}. 민간 takes precedence; the many
    공공/대규모/공공주택지구 combinations all collapse to 공공택지.
    """
    if not raw:
        return None
    s = str(raw)
    if "민간택지" in s or "민영" in s:
        return "민간택지"
    if any(k in s for k in ("공공택지", "공공주택", "대규모택지", "대규모 택지")):
        return "공공택지"
    return None


class GonggoRegulatory(BaseModel):
    """One row per launch (PBLANC) — its regulatory regime as printed in the 공고문."""

    pblanc_no: str
    notice_date: str | None = None       # 공고일 (RCRIT_PBLANC_DE) — leakage-guard basis
    supply_region: str | None = None     # 서울 / 경기 / ...

    jeonmae_raw: str | None = None        # 전매제한 as printed (guarded)
    jeonmae_months: int | None = None     # parsed; 없음 -> 0
    residence_raw: str | None = None      # 거주의무기간 as printed (guarded)
    residence_months: int | None = None   # parsed; 없음 -> 0
    price_ceiling: bool | None = None      # 분양가상한제 적용 여부 (적용 -> True)
    regulated_zone_raw: str | None = None  # 규제지역 as printed
    regulated_zone: str | None = None      # normalized: 투기과열/청약과열/조정대상/비규제
    land_type_raw: str | None = None       # 택지유형 as printed
    land_type: str | None = None           # normalized: 민간택지/공공택지

    source: str = "gonggo_pdf"

    @field_validator("jeonmae_raw", "residence_raw", mode="before")
    @classmethod
    def _guard_period(cls, v: object) -> str | None:
        return _clean_period(v if v is None else str(v))

    @field_validator("notice_date", mode="before")
    @classmethod
    def _notice_str(cls, v: object) -> str | None:
        # the applyhome lake stores 공고일 as a date; keep it as an ISO string here
        return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v is not None else None)

    @field_validator("price_ceiling", mode="before")
    @classmethod
    def _ceiling(cls, v: object) -> bool | None:
        if isinstance(v, bool) or v is None:
            return v
        s = str(v)
        if "미적용" in s:
            return False
        if "적용" in s:
            return True
        return None

    @model_validator(mode="after")
    def _derive(self) -> GonggoRegulatory:
        # months + normalized categoricals are derived from the (guarded) raw values;
        # computed here (not as field validators) so they fill from the raw inputs.
        if self.jeonmae_months is None:
            self.jeonmae_months = _to_months(self.jeonmae_raw)
        if self.residence_months is None:
            self.residence_months = _to_months(self.residence_raw)
        if self.regulated_zone is None:
            self.regulated_zone = _normalize_zone(self.regulated_zone_raw)
        if self.land_type is None:
            self.land_type = _normalize_land(self.land_type_raw)
        return self
