from django.db.models import Count, OuterRef, Prefetch, Subquery

from core.models import Symbol, Term, TermSymbol

from .semantic import (
    ENVIRONMENT_SCHEMA,
    ENVIRONMENT_TERM_LENGTH,
    ObservationValue,
    decode_environmental_term,
    encode_timestamp,
)


def environmental_term_queryset(*, start=None, end=None):
    """Return Terms matching the environment.v1 semantic shape.

    The schema marker and ordered TermSymbol relationships identify the
    semantic type. No decoded observation or secondary index is persisted.
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

    if start is not None:
        timestamp_terms = TermSymbol.objects.filter(
            order=1,
            symbol__symbol__gte=encode_timestamp(start),
        ).values("term_id")
        queryset = queryset.filter(pk__in=timestamp_terms)
    if end is not None:
        timestamp_terms = TermSymbol.objects.filter(
            order=1,
            symbol__symbol__lte=encode_timestamp(end),
        ).values("term_id")
        queryset = queryset.filter(pk__in=timestamp_terms)

    timestamp_blob = TermSymbol.objects.filter(
        term_id=OuterRef("pk"),
        order=1,
    ).values("symbol__symbol")[:1]
    return queryset.annotate(_timestamp_blob=Subquery(timestamp_blob)).order_by(
        "_timestamp_blob"
    )


def _decode_ordered_terms(terms):
    return sorted(
        (decode_environmental_term(term) for term in terms),
        key=lambda value: value.observed_at,
    )


def environmental_history(limit=48, *, start=None, end=None):
    """Return chronological environmental observations from the substrate."""
    values = _decode_ordered_terms(environmental_term_queryset(start=start, end=end))
    if limit is not None:
        values = values[-limit:]
    return values


async def environmental_history_iterator(*, start=None, end=None, chunk_size=1_000):
    """Asynchronously yield substrate observations in bounded chunks."""
    queryset = environmental_term_queryset(start=start, end=end)
    async for term in queryset.aiterator(chunk_size=chunk_size):
        yield decode_environmental_term(term)


def latest_environmental_observation():
    values = environmental_history(limit=1)
    return values[0] if values else None
