from django.core.management.base import BaseCommand

from measurements.services import save_environmental_observation


class Command(BaseCommand):
    help = "Record a sample reading without requiring sensor hardware."

    def add_arguments(self, parser):
        parser.add_argument("--temperature", type=float, default=21.5)
        parser.add_argument("--humidity", type=float, default=45.0)
        parser.add_argument("--pressure", type=float, default=1013.25)

    def handle(self, *args, **options):
        observation = save_environmental_observation(
            temperature_c=options["temperature"],
            relative_humidity=options["humidity"],
            pressure_hpa=options["pressure"],
        )
        self.stdout.write(self.style.SUCCESS(f"Recorded observation Term #{observation.pk}"))
