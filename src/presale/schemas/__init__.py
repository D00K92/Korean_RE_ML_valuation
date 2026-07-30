"""Pydantic schemas — every raw source is validated before landing to Parquet."""

from presale.schemas.applyhome import ApplyhomeRecord
from presale.schemas.ecos import EcosObservation
from presale.schemas.molit import MolitResaleRecord
from presale.schemas.school import SchoolRecord
from presale.schemas.schoolinfo import SchoolOutcomeRecord

__all__ = [
    "ApplyhomeRecord",
    "EcosObservation",
    "MolitResaleRecord",
    "SchoolOutcomeRecord",
    "SchoolRecord",
]
