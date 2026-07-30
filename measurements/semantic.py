import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntFlag

from django.db import transaction

from core.models import Symbol, Term, TermSymbol


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class AssessmentCheck(IntFlag):
    INPUTS_PLAUSIBLE = 1 << 0
    GAS_STABILIZED = 1 << 1
    HEATER_PROFILE_COMPLETE = 1 << 2
    TREND_PLAUSIBLE = 1 << 3
    ASSESSMENT_VALID = 1 << 4


@dataclass(frozen=True)
class ObservationValue:
    observed_at: datetime
    temperature_c: float
    relative_humidity: float
    pressure_hpa: float

    def as_dict(self):
        return {
            "kind": "environment",
            "recorded_at": self.observed_at.isoformat(),
            "temperature_c": self.temperature_c,
            "relative_humidity": self.relative_humidity,
            "pressure_hpa": self.pressure_hpa,
        }


@dataclass(frozen=True)
class AssessmentValue:
    observed_at: datetime
    percentage: int
    check: AssessmentCheck

    @property
    def valid(self):
        return bool(self.check & AssessmentCheck.ASSESSMENT_VALID)

    def as_dict(self):
        return {
            "kind": "air_quality",
            "recorded_at": self.observed_at.isoformat(),
            "air_quality_percentage": self.percentage,
            "check": int(self.check),
            "valid": self.valid,
        }


def encode_timestamp(value):
    if value.tzinfo is None:
        raise ValueError("Observation timestamps must be timezone-aware")
    delta = value.astimezone(timezone.utc) - EPOCH
    microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    return struct.pack(">q", microseconds)


def decode_timestamp(value):
    microseconds = struct.unpack(">q", value)[0]
    return EPOCH + timedelta(microseconds=microseconds)


def encode_temperature(value):
    encoded = round(float(value) * 100)
    if not -32768 <= encoded <= 32767:
        raise ValueError("Temperature is outside the canonical range")
    return struct.pack(">h", encoded)


def encode_humidity(value):
    encoded = round(float(value) * 100)
    if not 0 <= encoded <= 10_000:
        raise ValueError("Relative humidity must be between 0 and 100")
    return struct.pack(">H", encoded)


def encode_pressure(value):
    encoded = round(float(value) * 100)
    if not 0 <= encoded <= 0xFFFFFFFF:
        raise ValueError("Pressure is outside the canonical range")
    return struct.pack(">I", encoded)


def ordered_bytes(term):
    return [
        bytes(relation.symbol)
        for relation in term.termsymbol_set.select_related("symbol").order_by("order")
    ]


def create_term(atoms, symbol_cache=None):
    cache = symbol_cache if symbol_cache is not None else {}
    with transaction.atomic():
        term = Term.objects.create()
        relations = []
        for order, atom in enumerate(atoms):
            symbol = cache.get(atom)
            if symbol is None:
                result = Symbol.objects.get_or_create(symbol=atom)
                # The originating substrate manager returns a Symbol directly;
                # Django's stock manager returns (Symbol, created).
                symbol = result[0] if isinstance(result, tuple) else result
                cache[atom] = symbol
            relations.append(TermSymbol(term=term, symbol=symbol, order=order))
        TermSymbol.objects.bulk_create(relations)
    return term


def create_quick_check(
    observed_at,
    temperature_c,
    relative_humidity,
    pressure_hpa,
    *,
    symbol_cache=None,
):
    return create_term(
        (
            encode_timestamp(observed_at),
            encode_temperature(temperature_c),
            encode_pressure(pressure_hpa),
            encode_humidity(relative_humidity),
        ),
        symbol_cache,
    )


def create_air_quality_assessment(
    observed_at,
    percentage,
    check,
    *,
    symbol_cache=None,
):
    percentage = int(round(percentage))
    if not 0 <= percentage <= 100:
        raise ValueError("Air quality assessment must be between 0 and 100")
    check = AssessmentCheck(check)
    return create_term(
        (
            encode_timestamp(observed_at),
            struct.pack("B", percentage),
            struct.pack("B", int(check)),
        ),
        symbol_cache,
    )


def decode_quick_check(term):
    timestamp, temperature, pressure, humidity = ordered_bytes(term)
    return ObservationValue(
        observed_at=decode_timestamp(timestamp),
        temperature_c=struct.unpack(">h", temperature)[0] / 100,
        relative_humidity=struct.unpack(">H", humidity)[0] / 100,
        pressure_hpa=struct.unpack(">I", pressure)[0] / 100,
    )


def decode_air_quality_assessment(term):
    timestamp, percentage, check = ordered_bytes(term)
    return AssessmentValue(
        observed_at=decode_timestamp(timestamp),
        percentage=struct.unpack("B", percentage)[0],
        check=AssessmentCheck(struct.unpack("B", check)[0]),
    )
