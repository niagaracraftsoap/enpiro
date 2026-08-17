from django.test import TestCase

from .models import Symbol, Term, TermSymbol


class SubstrateTests(TestCase):
    def test_clear_symbols_are_shared(self):
        """Keep identical byte values canonical instead of duplicating symbols."""
        first = Symbol.objects.resolve_clear(b"temperature_c")
        second = Symbol.objects.resolve_clear(b"temperature_c")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Symbol.objects.filter(symbol=b"temperature_c").count(),
            1,
        )

    def test_symbol_batch_resolution_deduplicates_values(self):
        symbols, any_created = Symbol.objects.resolve_clear_many(
            [b"alpha", b"beta", b"alpha"]
        )

        self.assertTrue(any_created)
        self.assertEqual(
            [symbol.symbol for symbol in symbols],
            [b"alpha", b"beta", b"alpha"],
        )
        self.assertEqual(Symbol.objects.count(), 2)

    def test_single_blob_and_singleton_sequence_resolve_same_term(self):
        first = Term.objects.resolve_clear(b"alpha")
        second = Term.objects.resolve_clear([b"alpha"])

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            list(
                TermSymbol.objects.filter(term=first)
                .order_by("order")
                .values_list("symbol__symbol", flat=True)
            ),
            [b"alpha"],
        )

    def test_exact_ordered_sequence_resolves_existing_term(self):
        first = Term.objects.resolve_clear([b"alpha", b"beta"])
        second = Term.objects.resolve_clear([b"alpha", b"beta"])
        reverse = Term.objects.resolve_clear([b"beta", b"alpha"])

        self.assertEqual(first.pk, second.pk)
        self.assertNotEqual(first.pk, reverse.pk)
        self.assertEqual(Term.objects.count(), 2)

    def test_new_symbol_skips_term_lookup_and_creates_term(self):
        first = Term.objects.resolve_clear([b"alpha", b"beta"])
        second = Term.objects.resolve_clear([b"alpha", b"gamma"])

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(Term.objects.count(), 2)
        self.assertEqual(Symbol.objects.count(), 3)

    def test_repeated_symbol_values_keep_distinct_positions(self):
        term = Term.objects.resolve_clear([b"alpha", b"alpha"])

        self.assertEqual(
            list(
                TermSymbol.objects.filter(term=term)
                .order_by("order")
                .values_list("symbol__symbol", flat=True)
            ),
            [b"alpha", b"alpha"],
        )
