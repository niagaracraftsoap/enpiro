from .models import QuickCheckIndex
from .semantic import ObservationValue


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
