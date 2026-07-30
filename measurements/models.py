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


class EnvironmentalObservationManager(ShapedTermManager):
    symbol_count = 4


class AirQualityAssessmentManager(ShapedTermManager):
    symbol_count = 3


class EnvironmentalObservation(Term):
    """Semantic view: timestamp, temperature, humidity, pressure."""

    objects = EnvironmentalObservationManager()

    class Meta:
        proxy = True

    @property
    def value(self):
        from .semantic import decode_environmental_observation

        return decode_environmental_observation(self)


class AirQualityAssessment(Term):
    """Semantic view: timestamp, percentage, validation check flags."""

    objects = AirQualityAssessmentManager()

    class Meta:
        proxy = True

    @property
    def value(self):
        from .semantic import decode_air_quality_assessment

        return decode_air_quality_assessment(self)
