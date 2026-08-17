import csv
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Term
from measurements.semantic import ObservationValue, resolve_environmental_observation


FIELDNAMES = [
    "recorded_at",
    "temperature_c",
    "relative_humidity",
    "pressure_hpa",
]


class Command(BaseCommand):
    help = "Import a complete Enpiro CSV export into an empty dataset."

    def add_arguments(self, parser):
        parser.add_argument("path")

    @transaction.atomic
    def handle(self, *args, **options):
        if Term.objects.exists():
            raise CommandError("The dataset must be empty before importing readings.")

        imported = 0
        try:
            with open(options["path"], newline="", encoding="utf-8") as source:
                reader = csv.DictReader(source)
                if reader.fieldnames != FIELDNAMES:
                    raise CommandError("The CSV header is not a complete Enpiro export.")
                for line_number, row in enumerate(reader, start=2):
                    try:
                        resolve_environmental_observation(
                            ObservationValue(
                                observed_at=datetime.fromisoformat(row["recorded_at"]),
                                temperature_c=float(row["temperature_c"]),
                                relative_humidity=float(row["relative_humidity"]),
                                pressure_hpa=float(row["pressure_hpa"]),
                            )
                        )
                    except (TypeError, ValueError) as error:
                        raise CommandError(
                            f"Invalid reading on CSV line {line_number}: {error}"
                        ) from error
                    imported += 1
        except OSError as error:
            raise CommandError(f"Could not read CSV: {error}") from error

        self.stdout.write(self.style.SUCCESS(f"Imported {imported} readings."))
