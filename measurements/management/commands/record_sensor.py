from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from measurements.bme690_sensor import PimoroniBME690
from measurements.services import save_environmental_observation


class Command(BaseCommand):
    help = "Collect robustly averaged BME690 T/P/RH readings and store one Term."

    def add_arguments(self, parser):
        parser.add_argument(
            "--address",
            default=hex(settings.BME690_I2C_ADDRESS),
            help="I2C address configured by BME690_I2C_ADDRESS.",
        )
        parser.add_argument(
            "--samples",
            type=int,
            default=settings.BME690_SAMPLES_PER_OBSERVATION,
        )
        parser.add_argument(
            "--sample-interval",
            type=float,
            default=settings.BME690_SAMPLE_INTERVAL,
        )
        parser.add_argument(
            "--outlier-threshold",
            type=float,
            default=settings.BME690_OUTLIER_THRESHOLD,
            help="Modified z-score threshold (default: 3.5)",
        )

    def handle(self, *args, **options):
        try:
            sensor = PimoroniBME690(address=int(options["address"], 0))
            average = sensor.collect_average(
                samples=options["samples"],
                sample_interval=options["sample_interval"],
                outlier_threshold=options["outlier_threshold"],
            )
            term = save_environmental_observation(
                observed_at=average.observed_at,
                temperature_c=average.temperature_c,
                relative_humidity=average.relative_humidity,
                pressure_hpa=average.pressure_hpa,
            )
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            raise CommandError(f"BME690 observation failed: {error}") from error

        self.stdout.write(
            self.style.SUCCESS(
                f"Recorded observation Term #{term.pk}: "
                f"{average.temperature_c:.2f} C, "
                f"{average.pressure_hpa:.2f} hPa, "
                f"{average.relative_humidity:.2f} %RH "
                f"({average.retained_samples} retained, "
                f"{average.rejected_samples} rejected)"
            )
        )
