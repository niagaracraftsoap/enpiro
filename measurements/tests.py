import os
import struct
from datetime import datetime, timedelta, timezone
from django.conf import settings
from django.http import StreamingHttpResponse
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core.models import Symbol, Term

from .checks import check_condition_thresholds
from .semantic import (
    create_term,
    decode_environmental_term,
    ENVIRONMENT_SCHEMA,
    encode_humidity,
    encode_pressure,
    encode_temperature,
    encode_timestamp,
    ObservationValue,
    resolve_environmental_observation,
)
from .repository import environmental_history
from .services import save_environmental_observation


def resolve_reading(observed_at, temperature_c, relative_humidity, pressure_hpa):
    return resolve_environmental_observation(
        ObservationValue(
            observed_at=observed_at,
            temperature_c=temperature_c,
            relative_humidity=relative_humidity,
            pressure_hpa=pressure_hpa,
        )
    )


class SemanticEncodingTests(TestCase):
    def test_equal_values_share_symbols_across_terms(self):
        """Protect value deduplication without conflating unequal observations."""
        first = resolve_reading(
            datetime(2025, 7, 1, tzinfo=timezone.utc),
            21.25,
            48.0,
            1012.4,
        )
        second = resolve_reading(
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
        self.assertEqual(first_symbols[2], second_symbols[2])
        self.assertEqual(first_symbols[3], second_symbols[3])
        self.assertNotEqual(first_symbols[4], second_symbols[4])
        self.assertNotEqual(first_symbols[1], second_symbols[1])
        decoded = decode_environmental_term(first)
        self.assertEqual(decoded.temperature_c, 21.3)
        self.assertEqual(decoded.pressure_hpa, 1012.0)
        self.assertEqual(decoded.relative_humidity, 48.0)

    def test_measurements_have_quantized_two_byte_encodings(self):
        """Keep the documented compact precision and width of measurement atoms."""
        self.assertEqual(len(encode_temperature(21.25)), 2)
        self.assertEqual(len(encode_humidity(48.04)), 2)
        self.assertEqual(len(encode_pressure(1012.4)), 2)
        self.assertEqual(encode_temperature(21.34), encode_temperature(21.3))
        self.assertEqual(encode_humidity(48.04), encode_humidity(48.0))
        self.assertEqual(encode_pressure(1012.4), encode_pressure(1012))

    def test_repeated_values_create_only_one_symbol(self):
        """Ensure repeated observations benefit from substrate-level deduplication."""
        for minute in range(3):
            resolve_reading(
                datetime(2025, 7, 1, 0, minute, tzinfo=timezone.utc),
                21.25,
                48.0,
                1012.4,
            )
        self.assertEqual(Symbol.objects.filter(symbol=encode_temperature(21.25)).count(), 1)

    def test_legacy_precise_observations_remain_decodable(self):
        term = create_term(
            (
                ENVIRONMENT_SCHEMA,
                encode_timestamp(datetime(2025, 7, 1, tzinfo=timezone.utc)),
                struct.pack(">h", 2125),
                struct.pack(">I", 101240),
                struct.pack(">H", 4800),
            )
        )

        decoded = decode_environmental_term(term)

        self.assertEqual(decoded.temperature_c, 21.25)
        self.assertEqual(decoded.pressure_hpa, 1012.4)
        self.assertEqual(decoded.relative_humidity, 48.0)


class DashboardTests(TestCase):
    def test_admin_route_is_not_available(self):
        """Keep Django Admin out of the monitor's public URL surface."""
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 404)

    def test_empty_latest_endpoint_returns_404(self):
        """Give API clients an explicit no-data response before collection begins."""
        response = self.client.get(reverse("measurements:latest-reading"))
        self.assertEqual(response.status_code, 404)

    def test_dashboard_and_latest_api_show_environment(self):
        """Keep the initial page and latest API aligned with the stored observation."""
        save_environmental_observation(
            temperature_c=20.5,
            relative_humidity=42.0,
            pressure_hpa=1012.3,
        )
        response = self.client.get(reverse("measurements:latest-reading"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["environment"]["temperature_c"], 20.5)
        self.assertNotIn("air_quality", response.json())

        dashboard = self.client.get(reverse("measurements:dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.content.count(b'class="condition-indicator"'), 2)
        self.assertContains(dashboard, 'id="condition-thresholds"')
        self.assertEqual(
            dashboard.context["condition_thresholds"],
            settings.WAREHOUSE_CONDITION_THRESHOLDS,
        )
        self.assertContains(dashboard, "measurements/data-cache.js")
        self.assertContains(dashboard, "Localizing latest reading")
        for hours in (48, 72, 96):
            self.assertContains(dashboard, f'data-hours="{hours}"')
        self.assertLess(
            dashboard.content.index(b"measurements/data-cache.js"),
            dashboard.content.index(b"measurements/dashboard.js"),
        )

    def test_history_filters_metric_and_exports_csv(self):
        """Protect date filtering and the complete, restorable CSV export contract."""
        resolve_reading(
            datetime(2026, 7, 29, 12, tzinfo=timezone.utc),
            20.5,
            42,
            1012.3,
        )
        resolve_reading(
            datetime(2026, 7, 30, 12, tzinfo=timezone.utc),
            21.5,
            43,
            1011.8,
        )
        response = self.client.get(
            reverse("measurements:reading-history"),
            {
                "metric": "temperature_c",
                "start": "2026-07-30",
                "end": "2026-07-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["value"] for row in response.json()["readings"]], [21.5])

        response = self.client.get(
            reverse("measurements:reading-history"),
            {"metric": "all", "start": "2026-07-30", "end": "2026-07-30"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["readings"]), 1)
        self.assertEqual(response.json()["readings"][0]["temperature_c"], 21.5)
        self.assertEqual(
            response.json()["metrics"],
            ["temperature_c", "relative_humidity", "pressure_hpa"],
        )

        response = self.client.get(
            reverse("measurements:reading-history-csv"),
            {"metrics": "all"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response, StreamingHttpResponse)
        self.assertTrue(response.is_async)
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="warehouse-environment-history.csv"',
        )

    def test_history_without_explicit_range_is_limited_to_recent_year(self):
        now = datetime.now(timezone.utc)
        resolve_reading(
            now - timedelta(days=settings.INTERFACE_HISTORY_RETENTION_DAYS + 14),
            19.5,
            41,
            1008,
        )
        resolve_reading(
            now - timedelta(days=30),
            20.5,
            42,
            1012,
        )

        response = self.client.get(
            reverse("measurements:reading-history"),
            {"metric": "all"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["readings"]), 1)
        self.assertEqual(response.json()["readings"][0]["temperature_c"], 20.5)

    def test_history_rejects_ranges_older_than_interface_retention(self):
        response = self.client.get(
            reverse("measurements:reading-history"),
            {
                "metric": "all",
                "start": "2020-01-01",
                "end": "2020-01-31",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Use CSV export for older data.", response.json()["detail"])

    def test_history_filters_in_database_and_batches_symbol_loading(self):
        for day in range(1, 6):
            resolve_reading(
                datetime(2026, 7, day, 12, tzinfo=timezone.utc),
                20 + day,
                40 + day,
                1010 + day,
            )

        # One schema lookup, one Term query, and one prefetched relation query.
        with self.assertNumQueries(3):
            values = environmental_history(
                limit=None,
                start=datetime(2026, 7, 4, tzinfo=timezone.utc),
            )

        self.assertEqual([value.temperature_c for value in values], [24.0, 25.0])

    def test_history_rejects_invalid_metric_range_and_csv_selection(self):
        """Reject unsupported fields and ranges instead of returning misleading data."""
        self.assertEqual(
            self.client.get(
                reverse("measurements:reading-history"),
                {"metric": "air_quality"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                reverse("measurements:reading-history"),
                {"start": "2026-07-31", "end": "2026-07-30"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                reverse("measurements:reading-history-csv"),
                {"metrics": "temperature_c,air_quality"},
            ).status_code,
            400,
        )

    def test_reset_requires_post_and_both_confirmations(self):
        """Prevent recorded history from being erased by an incomplete reset request."""
        save_environmental_observation(
            temperature_c=20.5,
            relative_humidity=42.0,
            pressure_hpa=1012.3,
        )
        url = reverse("measurements:reset-readings")

        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(
            self.client.post(
                url,
                {
                    "confirmation": "RESET",
                    "password": "hardcodedresetpassword",
                },
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                url,
                {
                    "acknowledge_export": "yes",
                    "confirmation": "reset",
                    "password": "hardcodedresetpassword",
                },
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                url,
                {
                    "acknowledge_export": "yes",
                    "confirmation": "RESET",
                    "password": "wrong",
                },
            ).status_code,
            400,
        )
        self.assertEqual(Term.objects.count(), 1)

    def test_reset_deletes_terms_and_orphaned_symbols(self):
        """Verify a confirmed reset clears observations and unreferenced storage."""
        save_environmental_observation(
            temperature_c=20.5,
            relative_humidity=42.0,
            pressure_hpa=1012.3,
        )

        response = self.client.post(
            reverse("measurements:reset-readings"),
            {
                "acknowledge_export": "yes",
                "confirmation": "RESET",
                "password": "hardcodedresetpassword",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["terms_deleted"], 1)
        self.assertEqual(Term.objects.count(), 0)
        self.assertEqual(Symbol.objects.count(), 0)


class ConfigurationTests(SimpleTestCase):
    def test_default_condition_thresholds_are_ordered(self):
        """Keep the shipped condition bands valid under the application's own check."""
        self.assertEqual(check_condition_thresholds(None), [])

    @override_settings(
        WAREHOUSE_CONDITION_THRESHOLDS={
            "temperature_c": {
                "red_min": 5,
                "green_min": 25,
                "green_max": 15,
                "red_max": 30,
            },
            "relative_humidity": {
                "red_min": 25,
                "green_min": 35,
                "green_max": 60,
                "red_max": 70,
            },
        }
    )
    def test_invalid_condition_thresholds_fail_system_check(self):
        """Catch inverted condition bands during Django's deployment checks."""
        errors = check_condition_thresholds(None)
        self.assertEqual([error.id for error in errors], ["measurements.E001"])
