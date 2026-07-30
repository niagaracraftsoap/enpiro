import math
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError

from measurements.models import AirQualityAssessment, QuickCheck
from measurements.semantic import (
    AssessmentCheck,
    create_air_quality_assessment,
    create_quick_check,
)


def terms_in_period(model, start, end):
    for term in model.objects.iterator(chunk_size=250):
        observed_at = term.value.observed_at
        if start <= observed_at < end:
            yield term


class Command(BaseCommand):
    help = "Create plausible June–August demo Terms for Niagara Falls."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=2025)
        parser.add_argument("--interval-minutes", type=int, default=60)
        parser.add_argument("--seed", type=int, default=690)
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace environmental Terms within the selected summer.",
        )

    def handle(self, *args, **options):
        year = options["year"]
        interval = options["interval_minutes"]
        if not 1 <= interval <= 1440:
            raise CommandError("--interval-minutes must be between 1 and 1440")

        zone = ZoneInfo("America/Toronto")
        start = datetime(year, 6, 1, tzinfo=zone)
        end = datetime(year, 9, 1, tzinfo=zone)
        existing = [
            *terms_in_period(QuickCheck, start, end),
            *terms_in_period(AirQualityAssessment, start, end),
        ]
        if existing and not options["replace"]:
            raise CommandError(
                "Environmental Terms already exist in this period; use --replace."
            )
        if options["replace"]:
            for term in existing:
                term.delete()

        rng = random.Random(options["seed"])
        timestamp = start
        observation_count = 0
        assessment_count = 0
        weather_anomaly = 0.0
        pressure = 1013.0
        previous_day = None
        symbol_cache = {}
        assessment_every = 3

        while timestamp < end:
            if timestamp.date() != previous_day:
                weather_anomaly = weather_anomaly * 0.72 + rng.gauss(0, 2.1)
                previous_day = timestamp.date()

            progress = (timestamp - start).total_seconds() / (end - start).total_seconds()
            seasonal_mean = 19.4 + 3.0 * math.sin(math.pi * progress)
            diurnal = 4.6 * math.sin(2 * math.pi * (timestamp.hour - 9) / 24)
            temperature = seasonal_mean + weather_anomaly + diurnal + rng.gauss(0, 0.35)
            humidity = max(
                32,
                min(98, 68 - diurnal * 3.1 - weather_anomaly * 1.4 + rng.gauss(0, 3)),
            )
            pressure += rng.gauss(0, 0.38) + (1013.0 - pressure) * 0.018
            pressure = max(992, min(1032, pressure))

            create_quick_check(
                timestamp,
                temperature,
                humidity,
                pressure,
                symbol_cache=symbol_cache,
            )
            observation_count += 1

            # The gas measurement is transient. A slower assessment arrives
            # twenty minutes after every third hourly environmental sample.
            if (observation_count - 1) % assessment_every == 0:
                raw_index = 42 + max(0, humidity - 72) * 1.3 + rng.gauss(0, 8)
                if rng.random() < 0.012:
                    raw_index += rng.uniform(35, 110)
                percentage = round(max(0, min(100, 100 - raw_index / 2)))
                check = (
                    AssessmentCheck.INPUTS_PLAUSIBLE
                    | AssessmentCheck.GAS_STABILIZED
                    | AssessmentCheck.HEATER_PROFILE_COMPLETE
                    | AssessmentCheck.TREND_PLAUSIBLE
                    | AssessmentCheck.ASSESSMENT_VALID
                )
                create_air_quality_assessment(
                    timestamp + timedelta(minutes=20),
                    percentage,
                    check,
                    symbol_cache=symbol_cache,
                )
                assessment_count += 1

            timestamp += timedelta(minutes=interval)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {observation_count} observations and "
                f"{assessment_count} asynchronous air-quality assessments."
            )
        )
