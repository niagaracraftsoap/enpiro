from django.db import models
from django.db.models import Count

from core.models import Term


class ShapedTermManager(models.Manager):
    symbol_count = None

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(_semantic_symbol_count=Count("termsymbol"))
            .filter(_semantic_symbol_count=self.symbol_count)
        )


class QuickCheckManager(ShapedTermManager):
    symbol_count = 4


class QuickCheck(Term):
    """Semantic view: timestamp, temperature, pressure, humidity."""

    objects = QuickCheckManager()

    class Meta:
        proxy = True

    @property
    def value(self):
        from .semantic import decode_quick_check

        return decode_quick_check(self)


class QuickCheckIndex(models.Model):
    """Queryable projection of a semantic QuickCheck term."""

    term = models.OneToOneField(
        Term,
        on_delete=models.CASCADE,
        related_name="quick_check_index",
    )
    observed_at = models.DateTimeField(db_index=True)
    temperature_c = models.FloatField()
    relative_humidity = models.FloatField()
    pressure_hpa = models.FloatField()

    class Meta:
        ordering = ["observed_at"]
