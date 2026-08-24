from django.db.models import OuterRef, Prefetch, Subquery

from core.models import Term, TermSymbol

from .semantic import (
    ObservationValue,
    decode_environmental_term,
    encode_timestamp,
)


def environmental_term_queryset(*, start=None, end=None):
    """Return Terms matching the environment.v1 semantic shape.

    The schema marker and ordered TermSymbol relationships identify the
    semantic type. No decoded observation or secondary index is persisted.
    """
    timestamp_terms = TermSymbol.objects.filter(order=1)
    if start is not None:
        timestamp_terms = timestamp_terms.filter(
            symbol__symbol__gte=encode_timestamp(start),
        )
    if end is not None:
        timestamp_terms = timestamp_terms.filter(
            symbol__symbol__lte=encode_timestamp(end),
        )

    queryset = (
        Term.objects.filter(pk__in=timestamp_terms.values("term_id"))
        .prefetch_related(
            Prefetch(
                "termsymbol_set",
                queryset=TermSymbol.objects.select_related("symbol").order_by("order"),
                to_attr="_ordered_symbols",
            )
        )
    )

    timestamp_blob = TermSymbol.objects.filter(
        term_id=OuterRef("pk"),
        order=1,
    ).values("symbol__symbol")[:1]
    return queryset.annotate(_timestamp_blob=Subquery(timestamp_blob)).order_by(
        "_timestamp_blob"
    )


def _decode_ordered_terms(terms):
    values = []
    for term in terms:
        try:
            values.append(decode_environmental_term(term))
        except ValueError:
            continue
    return sorted(values, key=lambda value: value.observed_at)


def environmental_history(limit=48, *, start=None, end=None):
    """Return chronological environmental observations from the substrate."""
    values = _decode_ordered_terms(environmental_term_queryset(start=start, end=end))
    if limit is not None:
        values = values[-limit:]
    return values


def environmental_history_iterator(*, start=None, end=None, chunk_size=1_000):
    """Yield substrate observations in bounded database chunks."""
    queryset = environmental_term_queryset(start=start, end=end)
    for term in queryset.iterator(chunk_size=chunk_size):
        try:
            yield decode_environmental_term(term)
        except ValueError:
            continue


def latest_environmental_observation():
    timestamp_terms = (
        TermSymbol.objects.filter(order=1)
        .select_related("term")
        .prefetch_related(
            Prefetch(
                "term__termsymbol_set",
                queryset=TermSymbol.objects.select_related("symbol").order_by("order"),
                to_attr="_ordered_symbols",
            )
        )
        .order_by("-symbol__symbol", "-term_id")
    )
    # The normal case is one valid environmental term at the top. Keep a
    # small validation window so an unrelated or malformed term does not
    # prevent a usable environmental reading from being returned.
    for timestamp_relation in timestamp_terms[:100]:
        term = timestamp_relation.term
        try:
            return decode_environmental_term(term)
        except ValueError:
            continue
    return None
