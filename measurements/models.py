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


class AirQualityAssessmentManager(ShapedTermManager):
    symbol_count = 3


class QuickCheck(Term):
    """Semantic view: timestamp, temperature, pressure, humidity."""

    objects = QuickCheckManager()

    class Meta:
        proxy = True

    @property
    def value(self):
        from .semantic import decode_quick_check

        return decode_quick_check(self)


class AirQualityAssessment(Term):
    """Semantic view: timestamp, percentage, validation check flags."""

    objects = AirQualityAssessmentManager()

    class Meta:
        proxy = True

    @property
    def value(self):
        from .semantic import decode_air_quality_assessment

        return decode_air_quality_assessment(self)
