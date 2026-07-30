import csv
import tempfile
from datetime import datetime, timezone

from django.core.management import CommandError, call_command
from django.test import TestCase

from core.models import Term
from measurements.models import QuickCheck
from measurements.semantic import create_quick_check


class ImportReadingsTests(TestCase):
    def make_export(self):
        source = tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            suffix=".csv",
        )
        writer = csv.writer(source)
        writer.writerow(
            (
                "recorded_at",
                "temperature_c",
                "relative_humidity",
                "pressure_hpa",
            )
        )
        writer.writerow(("2026-07-30T18:00:00+00:00", "21.26", "48.04", "1012.4"))
        source.flush()
        return source

    def test_import_quantizes_a_complete_export(self):
        """Ensure exported history can be restored through canonical encoding."""
        with self.make_export() as source:
            call_command("import_readings_csv", source.name, verbosity=0)

        value = QuickCheck.objects.get().value
        self.assertEqual(value.observed_at, datetime(2026, 7, 30, 18, tzinfo=timezone.utc))
        self.assertEqual(value.temperature_c, 21.3)
        self.assertEqual(value.relative_humidity, 48.0)
        self.assertEqual(value.pressure_hpa, 1012.0)

    def test_import_refuses_a_nonempty_dataset(self):
        """Prevent an import from silently mixing with or duplicating stored history."""
        create_quick_check(
            datetime(2026, 7, 30, 18, tzinfo=timezone.utc),
            21,
            48,
            1012,
        )
        with self.make_export() as source:
            with self.assertRaisesMessage(CommandError, "must be empty"):
                call_command("import_readings_csv", source.name, verbosity=0)
        self.assertEqual(Term.objects.count(), 1)
