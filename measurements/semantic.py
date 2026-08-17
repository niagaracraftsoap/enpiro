import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from core.models import Symbol, Term, TermSymbol


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


ENVIRONMENT_SCHEMA = b"enpiro.environment.v1"
ENVIRONMENT_TERM_LENGTH = 5


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


def encode_environmental_observation(value):
    """Encode an environmental reading as an ordered substrate sequence."""
    return (
        ENVIRONMENT_SCHEMA,
        encode_timestamp(value.observed_at),
        encode_temperature(value.temperature_c),
        encode_pressure(value.pressure_hpa),
        encode_humidity(value.relative_humidity),
    )


def resolve_environmental_observation(value):
    """Resolve an environmental reading to its substrate Term."""
    from core.models import Term

    return Term.objects.resolve_clear(encode_environmental_observation(value))


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
    encoded = int(
        (Decimal(str(value)) * 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    if not -32768 <= encoded <= 32767:
        raise ValueError("Temperature is outside the canonical range")
    return struct.pack(">h", encoded)


def encode_humidity(value):
    encoded = int(
        (Decimal(str(value)) * 10).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    if not 0 <= encoded <= 1_000:
        raise ValueError("Relative humidity must be between 0 and 100")
    return struct.pack(">H", encoded)


def encode_pressure(value):
    encoded = int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if not 0 <= encoded <= 0xFFFF:
        raise ValueError("Pressure is outside the canonical range")
    return struct.pack(">H", encoded)


def ordered_bytes(term):
    prefetched = getattr(term, "_ordered_symbols", None)
    if prefetched is not None:
        return [bytes(relation.symbol) for relation in prefetched]
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
                symbol = Symbol.objects.resolve_clear(atom)
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
    from .models import QuickCheckIndex

    with transaction.atomic():
        term = create_term(
            (
                encode_timestamp(observed_at),
                encode_temperature(temperature_c),
                encode_pressure(pressure_hpa),
                encode_humidity(relative_humidity),
            ),
            symbol_cache,
        )
        value = decode_quick_check(term)
        QuickCheckIndex.objects.create(
            term=term,
            observed_at=value.observed_at,
            temperature_c=value.temperature_c,
            relative_humidity=value.relative_humidity,
            pressure_hpa=value.pressure_hpa,
        )
        return term


def decode_environmental_term(term):
    """Decode a Term with the environment.v1 semantic shape."""
    atoms = ordered_bytes(term)
    if len(atoms) != ENVIRONMENT_TERM_LENGTH:
        raise ValueError("Term is not an environment.v1 observation")
    if atoms[0] != ENVIRONMENT_SCHEMA:
        raise ValueError("Term has an unknown environmental schema")

    return ObservationValue(
        observed_at=decode_timestamp(atoms[1]),
        temperature_c=struct.unpack(">h", atoms[2])[0] / 10,
        pressure_hpa=float(struct.unpack(">H", atoms[3])[0]),
        relative_humidity=struct.unpack(">H", atoms[4])[0] / 10,
    )


def decode_quick_check(term):
    timestamp, temperature, pressure, humidity = ordered_bytes(term)
    # Preserve observations written by the older high-precision local branch
    # while all new readings use the compact production representation.
    if len(pressure) == 4:
        temperature_c = struct.unpack(">h", temperature)[0] / 100
        relative_humidity = struct.unpack(">H", humidity)[0] / 100
        pressure_hpa = struct.unpack(">I", pressure)[0] / 100
    else:
        temperature_c = struct.unpack(">h", temperature)[0] / 10
        relative_humidity = struct.unpack(">H", humidity)[0] / 10
        pressure_hpa = float(struct.unpack(">H", pressure)[0])
    return ObservationValue(
        observed_at=decode_timestamp(timestamp),
        temperature_c=temperature_c,
        relative_humidity=relative_humidity,
        pressure_hpa=pressure_hpa,
    )
