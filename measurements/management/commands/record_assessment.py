from django.core.management.base import BaseCommand

from measurements.semantic import AssessmentCheck
from measurements.services import save_air_quality_assessment


class Command(BaseCommand):
    help = "Record an asynchronous air-quality assessment for testing."

    def add_arguments(self, parser):
        parser.add_argument("percentage", type=int)
        parser.add_argument(
            "--unchecked",
            action="store_true",
            help="Record the assessment without the valid check flag.",
        )

    def handle(self, *args, **options):
        check = (
            AssessmentCheck(0)
            if options["unchecked"]
            else AssessmentCheck.ASSESSMENT_VALID
        )
        term = save_air_quality_assessment(
            percentage=options["percentage"],
            check=check,
        )
        self.stdout.write(self.style.SUCCESS(f"Recorded assessment Term #{term.pk}"))
