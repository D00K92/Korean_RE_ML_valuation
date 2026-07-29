"""Pydantic schemas — every raw source is validated before landing to Parquet."""

from presale.schemas.ecos import EcosObservation
from presale.schemas.molit import MolitResaleRecord
from presale.schemas.school import SchoolRecord

__all__ = ["EcosObservation", "MolitResaleRecord", "SchoolRecord"]
