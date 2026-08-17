"""Semantic air-quality assessments stored in the shared substrate."""

import struct
from dataclasses import dataclass
from datetime import datetime

from core.models import Term

from .semantic import (
    decode_timestamp,
    encode_timestamp,
)


AIR_QUALITY_TERM_LENGTH = 2


@dataclass(frozen=True)
class AirQualityAssessment:
    observed_at: datetime
    percentage: int

    def as_dict(self):
        return {
            "kind": "air_quality",
            "recorded_at": self.observed_at.isoformat(),
            "percentage": self.percentage,
        }


def encode_air_quality_assessment(value):
    if isinstance(value.percentage, bool) or not isinstance(value.percentage, int):
        raise ValueError("Air-quality percentage must be an integer")
    if not 0 <= value.percentage <= 100:
        raise ValueError("Air-quality percentage must be between 0 and 100")
    return (
        encode_timestamp(value.observed_at),
        struct.pack(">B", value.percentage),
    )


def resolve_air_quality_assessment(value):
    return Term.objects.resolve_clear(encode_air_quality_assessment(value))


def decode_air_quality_term(term):
    atoms = [bytes(relation.symbol) for relation in term.termsymbol_set.order_by("order")]
    if len(atoms) != AIR_QUALITY_TERM_LENGTH:
        raise ValueError("Term is not an air-quality assessment")
    if len(atoms[0]) != 8 or len(atoms[1]) != 1:
        raise ValueError("Term has an invalid air-quality shape")
    return AirQualityAssessment(
        observed_at=decode_timestamp(atoms[0]),
        percentage=struct.unpack(">B", atoms[1])[0],
    )
