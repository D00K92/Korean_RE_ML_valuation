"""Pydantic schemas — every raw source is validated before landing to Parquet."""

from data_pipeline.schemas.applyhome import ApplyhomeRecord
from data_pipeline.schemas.ecos import EcosObservation
from data_pipeline.schemas.gonggo import GonggoRegulatory
from data_pipeline.schemas.molit import MolitResaleRecord
from data_pipeline.schemas.school import SchoolRecord
from data_pipeline.schemas.schoolinfo import SchoolOutcomeRecord

__all__ = [
    "ApplyhomeRecord",
    "EcosObservation",
    "GonggoRegulatory",
    "MolitResaleRecord",
    "SchoolOutcomeRecord",
    "SchoolRecord",
]
