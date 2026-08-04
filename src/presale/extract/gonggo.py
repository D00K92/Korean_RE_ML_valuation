"""입주자모집공고문 PDF extractor — regulatory-regime ENRICHMENT source.

The 청약홈 odcloud API gives launch prices/units/dates but omits the regulatory
regime (전매제한 / 분양가상한제 / 실거주의무 / 규제지역). Those live only in the
입주자모집공고문 PDF. This module fetches that PDF for a launch and parses its compact
regulatory summary box into a validated `GonggoRegulatory` row.

Scope: **2024+ launches** (the summary box is format-consistent from 2024 on; older
docs scatter the fields in prose and are out of scope). LH 신혼희망타운/공공분양 often
publish image-only PDFs (no text layer) — those are skipped and land as null
(owner decision 2026-07-31; LightGBM handles nulls). See docs/gonggo_pdf_extraction.md.

Pipeline per launch:
  1. Fetch the 청약홈 detail page HTML and scrape its `getAtchmnfl.do` attachment link
     (the PDF URL is not in the API — it's only on the detail page).
  2. Download the PDF (cached on disk; the static host needs no API key).
  3. Parse the regulatory box: pdfplumber ruled-table first (label-anchored, robust to
     column drift), then a text-regex fallback for borderless boxes.
  4. Validate via the `GonggoRegulatory` pydantic model and land to Parquet.

No API key is used for the PDF download (public static host); the odcloud *listing*
that supplies PBLANC_NO uses the data.go.kr key via extract/applyhome.py.
"""

from __future__ import annotations

import io
import pathlib
import re
import time
from typing import Any

import httpx
import pandas as pd
from pypdf import PdfReader
from tenacity import retry, stop_after_attempt, wait_exponential

from presale.config import get_settings
from presale.schemas.gonggo import GonggoRegulatory

_SUBDIR = "gonggo"
_ATTACH_RE = re.compile(r"getAtchmnfl\.do\?[^\"')\s]+")
_MIN_TEXT = 1500  # a text-layer 공고문 extracts >100k chars; <1500 => image-only/stub

# Value patterns for the text-regex fallback (borderless boxes).
_CEILING_RE = re.compile(r"분양가\s*상한제[^가-힣]{0,10}(미?적용)")
_JEONMAE_TXT = re.compile(r"전매제한[^\n]{0,40}?(\d+\s*년|\d+\s*개월|없음)")
_RESIDE_TXT = re.compile(r"(?:거주의무|실거주)[^\n]{0,40}?(\d+\s*년|\d+\s*개월|없음)")
# 규제지역 / 택지유형 coverage fallback — searched only within the box region (around
# 분양가상한제) to avoid matching 투기과열지구 mentions elsewhere in the 공고문 prose.
_ZONE_RE = re.compile(
    r"(비규제\s*지역|비투기과열지구[^\n]{0,20}|투기과열지구[^\n]{0,12}|조정대상지역|청약과열지역)"
)
_LAND_RE = re.compile(r"(민간택지[^\n]{0,15}|공공택지[^\n]{0,20}|공공주택지구)")


def _box_region(text: str, radius: int = 400) -> str:
    """Text window around the 분양가상한제 anchor — the regulatory summary box."""
    i = text.find("분양가상한제")
    return text[max(0, i - radius):i + radius] if i >= 0 else text[:1500]


def _cfg() -> dict[str, Any]:
    return get_settings().get("sources", "applyhome", "gonggo", default={})


# --------------------------------------------------------------------------- #
# Fetch: detail page -> attachment URL -> PDF bytes (cached)
# --------------------------------------------------------------------------- #
@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, max=20), reraise=True)
def _get(url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    r = httpx.get(url, params=params, timeout=90, follow_redirects=True)
    if not r.is_success:  # never surface a URL that might carry a key
        raise RuntimeError(f"gonggo HTTP {r.status_code}")
    return r


def attachment_urls(detail_html: str) -> list[str]:
    """All `getAtchmnfl.do` links on a 청약홈 detail page, de-duplicated, absolute."""
    base = _cfg().get("attach_base", "https://static.applyhome.co.kr/ai/aia/")
    return [base + m for m in dict.fromkeys(_ATTACH_RE.findall(detail_html))]


def _pdf_text(b: bytes) -> str:
    try:
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages)
    except Exception:  # noqa: BLE001 — malformed/encrypted PDF -> treat as no text
        return ""


def download_gonggo(pblanc_no: str, house_manage_no: str) -> bytes | None:
    """Return the 모집공고문 PDF bytes for a launch (disk-cached), or None if none has
    a text layer. Picks the attachment whose text contains 분양가상한제 (the main 공고문);
    falls back to the largest text-layer PDF among the attachments.
    """
    cache = pathlib.Path(_cfg().get("cache_dir", "data/raw/gonggo/pdf_cache"))
    cache.mkdir(parents=True, exist_ok=True)
    cf = cache / f"{pblanc_no}.pdf"
    if cf.exists():
        return cf.read_bytes()

    params = {"houseManageNo": house_manage_no, "pblancNo": pblanc_no}
    html = _get(_cfg()["detail_page"], params).text
    best = b""
    for url in attachment_urls(html)[:8]:
        try:
            b = _get(url).content
        except Exception:  # noqa: BLE001 — skip a bad attachment, try the next
            continue
        if b[:4] != b"%PDF":
            continue
        t = _pdf_text(b)
        if len(t) > len(_pdf_text(best)):
            best = b
        if "분양가상한제" in t:  # the main 공고문 — stop early
            best = b
            break
        time.sleep(0.1)
    if len(_pdf_text(best)) < _MIN_TEXT:
        return None  # image-only / stub — skip (lands null)
    cf.write_bytes(best)
    return best


# --------------------------------------------------------------------------- #
# Parse: regulatory summary box -> field dict
# --------------------------------------------------------------------------- #
def _label_of(cell: str) -> str | None:
    """Map a header cell to our field name (None if not a regulatory header)."""
    if "전매제한" in cell:
        return "jeonmae_raw"
    if "거주의무" in cell or "거주 의무" in cell:
        return "residence_raw"
    if "분양가상한제" in cell:
        return "price_ceiling"
    if "택지" in cell and "유형" in cell:
        return "land_type_raw"
    if any(k in cell for k in ("투기과열", "청약과열", "조정대상", "규제지역")):
        return "regulated_zone_raw"
    return None


def _parse_box_table(pdf_bytes: bytes) -> dict[str, str]:
    """Label-anchored parse of the ruled summary box: for each header cell, take the
    cell directly beneath it (same column). Robust to varying column counts/order.
    """
    import pdfplumber  # local import: heavy, only needed here

    out: dict[str, str] = {}
    try:
        pdf_ctx = pdfplumber.open(io.BytesIO(pdf_bytes))
    except Exception:  # noqa: BLE001 — corrupt/truncated PDF -> no table (skip, don't crash)
        return out
    with pdf_ctx as pdf:
        for page in pdf.pages[:7]:  # the box sits near the top of the 공고문
            try:
                if "분양가상한제" not in (page.extract_text() or ""):
                    continue
                tables = page.extract_tables()
            except Exception:  # noqa: BLE001 — a malformed page: skip it, keep going
                continue
            for table in tables:
                cells = [[(c or "").replace("\n", "").strip() for c in row] for row in table]
                if not any("분양가상한제" in c for row in cells for c in row):
                    continue
                for ri, row in enumerate(cells):
                    for ci, cell in enumerate(row):
                        label = _label_of(cell)
                        if label and ri + 1 < len(cells) and ci < len(cells[ri + 1]):
                            val = cells[ri + 1][ci].strip()
                            if val and label not in out:
                                out[label] = val
                if out.get("price_ceiling") or out.get("jeonmae_raw"):
                    return out
    return out


def _fill_zone_land(fields: dict[str, str], text: str) -> None:
    """Fill 규제지역/택지유형 from the box region when the table parse missed them."""
    region = _box_region(text)
    if not fields.get("regulated_zone_raw") and (m := _ZONE_RE.search(region)):
        fields["regulated_zone_raw"] = m.group(0).strip()
    if not fields.get("land_type_raw") and (m := _LAND_RE.search(region)):
        fields["land_type_raw"] = m.group(0).strip()


def _parse_box_text(text: str) -> dict[str, str]:
    """Text-regex fallback for borderless boxes (pdfplumber finds no ruled table)."""
    out: dict[str, str] = {}
    if (m := _CEILING_RE.search(text)):
        out["price_ceiling"] = m.group(1)
    if (m := _JEONMAE_TXT.search(text)):
        out["jeonmae_raw"] = m.group(1).strip()
    if (m := _RESIDE_TXT.search(text)):
        out["residence_raw"] = m.group(1).strip()
    _fill_zone_land(out, text)
    return out


def parse_regulatory(pdf_bytes: bytes, pblanc_no: str, **meta: Any) -> GonggoRegulatory | None:
    """Parse one 공고문's regulatory box -> validated row (None if nothing found)."""
    text = _pdf_text(pdf_bytes)
    fields = _parse_box_table(pdf_bytes)
    if not (fields.get("price_ceiling") or fields.get("jeonmae_raw")):
        fields = _parse_box_text(text)
    if not (fields.get("price_ceiling") or fields.get("jeonmae_raw")):
        return None
    _fill_zone_land(fields, text)   # lift zone/land coverage when the table missed them
    return GonggoRegulatory(pblanc_no=pblanc_no, **fields, **meta)


# --------------------------------------------------------------------------- #
# Public API: fetch + parse a set of launches, land to Parquet
# --------------------------------------------------------------------------- #
def extract(launches: pd.DataFrame) -> pd.DataFrame:
    """Fetch + parse regulatory facts for the given launches, land to Parquet.

    `launches` needs columns: pblanc_no, house_manage_no (PBLANC_NO / HOUSE_MANAGE_NO
    from extract/applyhome.py), optionally notice_date + supply_region for the join.
    Rows that are image-only / unparseable are skipped (they simply carry null
    regulatory features downstream). Returns the parsed frame.
    """
    records: list[GonggoRegulatory] = []
    for r in launches.itertuples(index=False):
        pblanc = str(r.pblanc_no)
        try:
            b = download_gonggo(pblanc, str(r.house_manage_no))
            if b is None:
                continue
            rec = parse_regulatory(
                b, pblanc,
                notice_date=getattr(r, "notice_date", None),
                supply_region=getattr(r, "supply_region", None),
            )
        except Exception:  # noqa: BLE001 — one bad launch never aborts the batch
            continue
        if rec is not None:
            records.append(rec)
    df = pd.DataFrame([rec.model_dump() for rec in records])
    if not df.empty:
        out = pathlib.Path(get_settings().get("paths", "raw_dir", default="data/raw")) / _SUBDIR
        out.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out / "data.parquet", index=False)
    return df
