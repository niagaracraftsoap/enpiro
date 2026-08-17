import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from core.models import Symbol, Term, TermSymbol


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


LOCAL_SOURCE_ID = "local"
ENVIRONMENT_TERM_LENGTH = 5


@dataclass(frozen=True)
class ObservationValue:
    observed_at: datetime
    temperature_c: float
    relative_humidity: float
    pressure_hpa: float
    source_id: str = LOCAL_SOURCE_ID

    def as_dict(self):
        return {
            "kind": "environment",
            "source_id": self.source_id,
            "recorded_at": self.observed_at.isoformat(),
            "temperature_c": self.temperature_c,
            "relative_humidity": self.relative_humidity,
            "pressure_hpa": self.pressure_hpa,
        }


def encode_source_id(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Source ID must be a non-empty string")
    encoded = value.encode("utf-8")
    if len(encoded) > 65_535:
        raise ValueError("Source ID is too long")
    return encoded


def encode_environmental_observation(value):
    """Encode an environmental reading as an ordered substrate sequence."""
    return (
        encode_source_id(value.source_id),
        encode_timestamp(value.observed_at),
        encode_temperature(value.temperature_c),
        encode_pressure(value.pressure_hpa),
        encode_humidity(value.relative_humidity),
    )


def resolve_environmental_observation(value):
    """Resolve an environmental reading to its substrate Term."""
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


def decode_environmental_term(term):
    """Decode a source-aware environmental Term."""
    atoms = ordered_bytes(term)
    if len(atoms) != ENVIRONMENT_TERM_LENGTH:
        raise ValueError("Term is not an environmental observation")

    try:
        source_id = atoms[0].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Term has an invalid source ID") from error

    if len(atoms[1]) != 8 or len(atoms[2]) != 2 or len(atoms[4]) != 2:
        raise ValueError("Term has an invalid environmental shape")
    temperature = struct.unpack(">h", atoms[2])[0]
    if len(atoms[3]) == 4:
        # Terms written before the canonical compact profile used hundredths.
        pressure_hpa = struct.unpack(">I", atoms[3])[0] / 100
        relative_humidity = struct.unpack(">H", atoms[4])[0] / 100
        temperature_c = temperature / 100
    else:
        temperature_c = temperature / 10
        pressure_hpa = float(struct.unpack(">H", atoms[3])[0])
        relative_humidity = struct.unpack(">H", atoms[4])[0] / 10

    return ObservationValue(
        observed_at=decode_timestamp(atoms[1]),
        temperature_c=temperature_c,
        relative_humidity=relative_humidity,
        pressure_hpa=pressure_hpa,
        source_id=source_id,
    )
