from django.db import transaction
from django.utils import timezone

from core.models import Symbol, Term

from .semantic import create_quick_check


def save_quick_check(
    *,
    observed_at=None,
    temperature_c,
    relative_humidity,
    pressure_hpa,
):
    term = create_quick_check(
        observed_at or timezone.now(),
        temperature_c,
        relative_humidity,
        pressure_hpa,
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
