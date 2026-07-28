"""Schema tests for ECOS macro observations."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from presale.schemas import EcosObservation


def test_valid_observation_coerces_value():
    obs = EcosObservation(series="base_rate", deal_ym="202401", value="3.5", unit="연%")
    assert obs.value == 3.5
    assert obs.deal_ym == "202401"


def test_value_strips_commas():
    obs = EcosObservation(series="m2", deal_ym="202401", value="3,725,946.1", unit="십억원")
    assert obs.value == pytest.approx(3_725_946.1)


def test_bad_month_rejected():
    with pytest.raises(ValidationError):
        EcosObservation(series="base_rate", deal_ym="2024", value="3.5")
    with pytest.raises(ValidationError):
        EcosObservation(series="base_rate", deal_ym="202413", value="3.5")  # month 13


def test_empty_value_rejected():
    with pytest.raises(ValidationError):
        EcosObservation(series="base_rate", deal_ym="202401", value="")
