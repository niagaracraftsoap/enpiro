from datetime import datetime, timezone

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import AirQualityAssessment, EnvironmentalObservation
from .semantic import (
    AssessmentCheck,
    create_air_quality_assessment,
    create_environmental_observation,
    encode_temperature,
)
from .services import save_environmental_observation


class SemanticEncodingTests(TestCase):
    def test_equal_values_share_symbols_across_terms(self):
        first = create_environmental_observation(
            datetime(2025, 7, 1, tzinfo=timezone.utc),
            21.25,
            48.0,
            1012.4,
        )
        second = create_environmental_observation(
            datetime(2025, 7, 1, 0, 10, tzinfo=timezone.utc),
            21.25,
            50.0,
            1012.4,
        )
        first_symbols = list(
            first.termsymbol_set.order_by("order").values_list("symbol_id", flat=True)
        )
        second_symbols = list(
            second.termsymbol_set.order_by("order").values_list("symbol_id", flat=True)
        )
        self.assertEqual(first_symbols[1], second_symbols[1])
        self.assertEqual(first_symbols[3], second_symbols[3])
        self.assertNotEqual(first_symbols[0], second_symbols[0])

    def test_temperature_has_canonical_two_byte_encoding(self):
        self.assertEqual(len(encode_temperature(21.25)), 2)

    def test_air_quality_is_an_independent_term(self):
        assessment = create_air_quality_assessment(
            datetime(2025, 7, 1, 0, 20, tzinfo=timezone.utc),
            87,
            AssessmentCheck.ASSESSMENT_VALID,
        )
        value = AirQualityAssessment.objects.get(pk=assessment.pk).value
        self.assertEqual(value.percentage, 87)
        self.assertTrue(value.valid)


class DashboardTests(TestCase):
    def test_empty_latest_endpoint_returns_404(self):
        response = self.client.get(reverse("measurements:latest-reading"))
        self.assertEqual(response.status_code, 404)

    def test_dashboard_and_api_join_latest_independent_streams(self):
        save_environmental_observation(
            temperature_c=20.5,
            relative_humidity=42.0,
            pressure_hpa=1012.3,
        )
        create_air_quality_assessment(
            datetime.now(timezone.utc),
            91,
            AssessmentCheck.ASSESSMENT_VALID,
        )
        response = self.client.get(reverse("measurements:latest-reading"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["environment"]["temperature_c"], 20.5)
        self.assertEqual(
            response.json()["air_quality"]["air_quality_percentage"],
            91,
        )


class SeedSummerTests(TestCase):
    def test_creates_asynchronous_semantic_terms(self):
        call_command("seed_summer", year=2025, interval_minutes=1440, verbosity=0)
        self.assertEqual(EnvironmentalObservation.objects.count(), 92)
        self.assertLess(
            AirQualityAssessment.objects.count(),
            EnvironmentalObservation.objects.count(),
        )
