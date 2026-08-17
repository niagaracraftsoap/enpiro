from datetime import datetime, timezone

from django.test import TestCase

from core.models import TermSymbol

from .air_quality import (
    AirQualityAssessment,
    decode_air_quality_term,
    encode_air_quality_assessment,
    resolve_air_quality_assessment,
)


class AirQualitySemanticTests(TestCase):
    def test_assessment_is_an_independent_ordered_term(self):
        assessment = AirQualityAssessment(
            observed_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
            percentage=72,
        )
        term = resolve_air_quality_assessment(assessment)

        self.assertEqual(TermSymbol.objects.filter(term=term).count(), 2)
        self.assertEqual(decode_air_quality_term(term), assessment)

    def test_percentage_is_required_to_be_an_integer_between_zero_and_one_hundred(self):
        for percentage in (-1, 101, 72.5, None):
            with self.subTest(percentage=percentage):
                with self.assertRaises(ValueError):
                    encode_air_quality_assessment(
                        AirQualityAssessment(
                            observed_at=datetime(2026, 8, 17, tzinfo=timezone.utc),
                            percentage=percentage,
                        )
                    )
