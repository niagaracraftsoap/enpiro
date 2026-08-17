from django.db import transaction
from django.utils import timezone

from core.models import Symbol, Term

from .semantic import LOCAL_SOURCE_ID, ObservationValue, resolve_environmental_observation


def save_environmental_observation(
    *,
    observed_at=None,
    temperature_c,
    relative_humidity,
    pressure_hpa,
    source_id=LOCAL_SOURCE_ID,
):
    term = resolve_environmental_observation(
        ObservationValue(
            observed_at=observed_at or timezone.now(),
            temperature_c=temperature_c,
            relative_humidity=relative_humidity,
            pressure_hpa=pressure_hpa,
            source_id=source_id,
        )
    )
    return term


@transaction.atomic
def reset_dataset():
    """Delete recorded terms and symbols no longer referenced by any term."""
    term_count = Term.objects.count()
    Term.objects.all().delete()
    orphaned_symbols = Symbol.objects.filter(termsymbol__isnull=True)
    symbol_count = orphaned_symbols.count()
    orphaned_symbols.delete()
    return term_count, symbol_count
