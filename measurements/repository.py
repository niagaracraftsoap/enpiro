from .models import QuickCheck


def _recent_values(model, limit):
    terms = list(model.objects.order_by("-pk")[:limit])
    return [term.value for term in reversed(terms)]


def environmental_history(limit=48, *, start=None, end=None):
    if start is None and end is None:
        return _recent_values(QuickCheck, limit)

    values = []
    for term in QuickCheck.objects.order_by("pk").iterator(chunk_size=250):
        value = term.value
        if start is not None and value.observed_at < start:
            continue
        if end is not None and value.observed_at > end:
            continue
        values.append(value)
    return values[-limit:] if limit is not None else values


def latest_environmental_observation():
    term = QuickCheck.objects.order_by("-pk").first()
    return term.value if term else None
