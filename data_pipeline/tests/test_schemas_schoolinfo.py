"""Schema tests for the 학교알리미 SchoolOutcomeRecord model."""

from __future__ import annotations

from data_pipeline.schemas.schoolinfo import SchoolOutcomeRecord


def test_schema_parses_rate_and_requires_name():
    r = SchoolOutcomeRecord(
        school_code="S1",
        name="대치고",
        hs_type="자율고등학교",
        grad_rate="88.5",
        emd_code="1168010600",
        sigungu_code="11680",
    )
    assert r.grad_rate == 88.5
    # blank grad_rate -> None, not a crash
    r2 = SchoolOutcomeRecord(school_code="S2", name="x", grad_rate="", sigungu_code="11680")
    assert r2.grad_rate is None
