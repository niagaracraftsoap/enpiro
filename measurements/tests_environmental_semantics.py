from datetime import datetime, timezone

from django.test import TestCase

from core.models import Term, TermSymbol

from .repository import environmental_history
from .semantic import (
    create_term,
    ObservationValue,
    decode_environmental_term,
    encode_environmental_observation,
    resolve_environmental_observation,
)


class EnvironmentalSemanticSubstrateTests(TestCase):
    def setUp(self):
        self.observation = ObservationValue(
            observed_at=datetime(2026, 8, 17, 12, 30, tzinfo=timezone.utc),
            temperature_c=22.4,
            relative_humidity=51.2,
            pressure_hpa=1013,
        )

    def test_environmental_observation_is_a_marked_ordered_term(self):
        term = resolve_environmental_observation(self.observation)

        self.assertEqual(TermSymbol.objects.filter(term=term).count(), 5)
        self.assertEqual(
            list(term.termsymbol_set.order_by("order").values_list("symbol__symbol", flat=True))[0],
            b"local",
        )
        self.assertEqual(decode_environmental_term(term), self.observation)

    def test_source_id_is_part_of_the_ordered_term(self):
        observation = ObservationValue(
            observed_at=self.observation.observed_at,
            temperature_c=self.observation.temperature_c,
            relative_humidity=self.observation.relative_humidity,
            pressure_hpa=self.observation.pressure_hpa,
            source_id="pico-01",
        )
        term = resolve_environmental_observation(observation)

        self.assertEqual(decode_environmental_term(term).source_id, "pico-01")
        self.assertNotEqual(term.pk, resolve_environmental_observation(self.observation).pk)

    def test_identical_environmental_observation_reuses_term(self):
        first = resolve_environmental_observation(self.observation)
        second = resolve_environmental_observation(self.observation)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Term.objects.count(), 1)

    def test_substrate_query_excludes_unmarked_terms(self):
        environmental_term = resolve_environmental_observation(self.observation)
        create_term(encode_environmental_observation(self.observation)[1:])

        terms = list(environmental_history(limit=None))

        self.assertEqual(
            [value.observed_at for value in terms],
            [self.observation.observed_at],
        )
        self.assertEqual(terms[0], decode_environmental_term(environmental_term))
