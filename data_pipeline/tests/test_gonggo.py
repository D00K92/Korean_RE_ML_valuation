"""Tests for the 입주자모집공고문 regulatory parser — pure logic, no network.

Covers value normalisation (년/개월/없음 -> months, 적용 -> bool), the 규제지역/택지유형
categorical collapse, the contamination guards (boilerplate prose / wrong-column '미적용'
rejected), the text-regex fallback, attachment-URL scraping, and the internal-coherence
property that gives confidence without an API ground truth (상한제 적용 => 실거주의무).
"""

from __future__ import annotations

from data_pipeline.ingestion import gonggo
from data_pipeline.schemas.gonggo import (
    GonggoRegulatory,
    _normalize_land,
    _normalize_zone,
    _to_months,
)


def test_to_months():
    assert _to_months("3년") == 36
    assert _to_months("6개월") == 6
    assert _to_months("1년 6개월") == 18
    assert _to_months("없음") == 0
    assert _to_months("소유권이전등기일까지(다만, 그 기간이 3년을 초과하는 경우 3년)") == 36
    assert _to_months(None) is None
    assert _to_months("해당사항") is None


def test_schema_normalisation():
    r = GonggoRegulatory(
        pblanc_no="2024000176",
        jeonmae_raw="3년",
        residence_raw="없음",
        price_ceiling="미적용",
        regulated_zone_raw="비규제지역(비투기과열지구, 비청약과열지역)",
        land_type_raw="공공택지, 대규모택지개발지구",
    )
    assert r.jeonmae_months == 36
    assert r.residence_months == 0
    assert r.price_ceiling is False
    assert r.regulated_zone == "비규제"  # collapsed from the parenthetical variant
    assert r.land_type == "공공택지"  # collapsed from the combination


def test_price_ceiling_variants():
    assert GonggoRegulatory(pblanc_no="x", price_ceiling="적용").price_ceiling is True
    assert GonggoRegulatory(pblanc_no="x", price_ceiling="미적용").price_ceiling is False
    assert GonggoRegulatory(pblanc_no="x", price_ceiling="해당없음").price_ceiling is None


def test_normalize_zone():
    assert _normalize_zone("투기과열지구/청약과열지역") == "투기과열"
    assert _normalize_zone("투기과열지구 / 청약과열지역") == "투기과열"
    assert _normalize_zone("비규제 지역") == "비규제"
    assert _normalize_zone("비투기과열지구 / 비청약과열지역") == "비규제"  # negated => 비규제
    assert _normalize_zone("조정대상지역") == "조정대상"
    assert _normalize_zone(None) is None


def test_normalize_land():
    assert _normalize_land("민간택지 / 대규모 택지개발지구") == "민간택지"  # 민간 precedence
    assert _normalize_land("민영주택 / 민간택지") == "민간택지"
    assert _normalize_land("공공택지(대규모 택지개발지구)") == "공공택지"
    assert _normalize_land("대규모택지개발지구 및 공공택지 /공공주택지구") == "공공택지"
    assert _normalize_land(None) is None


def test_period_contamination_guard():
    """A boilerplate paragraph or a wrong-column '미적용' must not become a period."""
    boiler = GonggoRegulatory(
        pblanc_no="x",
        jeonmae_raw="1 공통유의 사항 한국부동산원 청약홈 콜센터는 ... 최초 입주자모집공고일은 ...",
        residence_raw="미적용",  # bled in from the 분양가상한제 column
        price_ceiling="미적용",
    )
    assert boiler.jeonmae_raw is None and boiler.jeonmae_months is None
    assert boiler.residence_raw is None and boiler.residence_months is None
    # a genuine parenthetical period survives the guard
    ok = GonggoRegulatory(pblanc_no="y", jeonmae_raw="3년(단, 소유권이전등기를 완료한 때까지)")
    assert ok.jeonmae_months == 36


def test_regime_coherence():
    """분양가상한제 적용 launches carry a 실거주의무 — the coherence check we rely on."""
    ceiling = GonggoRegulatory(pblanc_no="x", price_ceiling="적용", residence_raw="3년")
    market = GonggoRegulatory(pblanc_no="y", price_ceiling="미적용", residence_raw="없음")
    assert ceiling.price_ceiling and ceiling.residence_months and ceiling.residence_months > 0
    assert market.price_ceiling is False and market.residence_months == 0


def test_text_fallback_borderless_box():
    text = (
        "■ 규제사항 안내\n"
        "본 아파트는 분양가상한제 미적용 주택이며, 비규제지역에 해당합니다. 택지유형: 민간택지.\n"
        "전매제한 기간은 6개월이며, 거주의무 기간은 없음 입니다.\n"
    )
    out = gonggo._parse_box_text(text)
    assert out["price_ceiling"] == "미적용"
    assert out["jeonmae_raw"] == "6개월"
    assert out["residence_raw"] == "없음"
    assert "비규제" in out["regulated_zone_raw"]
    assert "민간택지" in out["land_type_raw"]


def test_attachment_url_scrape():
    html = (
        'foo <a href="getAtchmnfl.do?houseManageNo=2024000176&pblancNo=2024000176'
        '&atchmnflSeqNo=111&atchmnflSn=1">공고문</a> dup '
        "getAtchmnfl.do?houseManageNo=2024000176&pblancNo=2024000176&atchmnflSeqNo=111&atchmnflSn=1"
    )
    urls = gonggo.attachment_urls(html)
    assert len(urls) == 1
    assert urls[0].startswith("https://static.applyhome.co.kr/ai/aia/getAtchmnfl.do?")


def test_corrupt_pdf_is_skipped_not_fatal():
    """A truncated/corrupt PDF must yield None, never raise (one bad doc can't abort
    a whole batch — the failure mode that crashed the Jeju enrichment run)."""
    junk = b"%PDF-1.4\nnot really a pdf, truncated"
    assert gonggo._parse_box_table(junk) == {}
    assert gonggo.parse_regulatory(junk, "9999") is None


def test_label_of():
    assert gonggo._label_of("전매제한") == "jeonmae_raw"
    assert gonggo._label_of("거주의무기간") == "residence_raw"
    assert gonggo._label_of("분양가상한제") == "price_ceiling"
    assert gonggo._label_of("투기과열지구/청약과열지역") == "regulated_zone_raw"
    assert gonggo._label_of("택지유형") == "land_type_raw"
    assert gonggo._label_of("공급금액") is None
