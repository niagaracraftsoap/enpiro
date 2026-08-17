from django.db.models import Count, Prefetch

from core.models import Symbol, Term, TermSymbol

from .models import QuickCheckIndex
from .semantic import (
    ENVIRONMENT_SCHEMA,
    ENVIRONMENT_TERM_LENGTH,
    ObservationValue,
    decode_environmental_term,
)


def _value(index):
    return ObservationValue(
        observed_at=index.observed_at,
        temperature_c=index.temperature_c,
        relative_humidity=index.relative_humidity,
        pressure_hpa=index.pressure_hpa,
    )


def _history_queryset(*, start=None, end=None):
    queryset = QuickCheckIndex.objects.all()
    if start is not None:
        queryset = queryset.filter(observed_at__gte=start)
    if end is not None:
        queryset = queryset.filter(observed_at__lte=end)
    return queryset


def _recent_values(limit):
    rows = list(QuickCheckIndex.objects.order_by("-observed_at")[:limit])
    return [_value(row) for row in reversed(rows)]


def environmental_history(limit=48, *, start=None, end=None):
    if start is None and end is None:
        return _recent_values(limit)

    queryset = _history_queryset(start=start, end=end)
    if limit is not None:
        queryset = queryset.order_by("-observed_at")[:limit]
        return [_value(row) for row in reversed(list(queryset))]
    return [_value(row) for row in queryset]


async def environmental_history_iterator(*, start=None, end=None, chunk_size=1_000):
    """Asynchronously yield an ordered range in bounded database chunks."""
    rows = _history_queryset(start=start, end=end).aiterator(chunk_size=chunk_size)
    async for row in rows:
        yield _value(row)


def latest_environmental_observation():
    row = QuickCheckIndex.objects.order_by("-observed_at").first()
    return _value(row) if row else None


def environmental_term_queryset(*, start=None, end=None):
    """Return substrate Terms carrying the environment.v1 semantic shape.

    The schema marker and ordered TermSymbol relations identify the semantic
    type. No decoded observation or secondary index is persisted.
    """
    schema_symbol = Symbol.objects.filter(symbol=ENVIRONMENT_SCHEMA).first()
    if schema_symbol is None:
        return Term.objects.none()

    matching_symbols = TermSymbol.objects.filter(
        order=0,
        symbol_id=schema_symbol.pk,
    ).values("term_id")
    queryset = (
        Term.objects.filter(pk__in=matching_symbols)
        .annotate(_symbol_count=Count("termsymbol"))
        .filter(_symbol_count=ENVIRONMENT_TERM_LENGTH)
        .prefetch_related(
            Prefetch(
                "termsymbol_set",
                queryset=TermSymbol.objects.select_related("symbol").order_by("order"),
                to_attr="_ordered_symbols",
            )
        )
    )

    if start is not None or end is not None:
        timestamp_symbols = TermSymbol.objects.filter(
            order=1,
            symbol__symbol__isnull=False,
        )
        if start is not None:
            from .semantic import encode_timestamp

            timestamp_symbols = timestamp_symbols.filter(
                symbol__symbol__gte=encode_timestamp(start)
            )
        if end is not None:
            from .semantic import encode_timestamp

            timestamp_symbols = timestamp_symbols.filter(
                symbol__symbol__lte=encode_timestamp(end)
            )
        queryset = queryset.filter(pk__in=timestamp_symbols.values("term_id"))

    return queryset


def environmental_history_from_substrate(limit=48, *, start=None, end=None):
    """Read environmental observations from Terms, decoding only at the boundary."""
    terms = list(environmental_term_queryset(start=start, end=end))
    values = sorted(
        (decode_environmental_term(term) for term in terms),
        key=lambda value: value.observed_at,
    )
    if limit is not None:
        values = values[-limit:]
    return values
