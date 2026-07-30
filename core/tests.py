from django.test import TestCase

from .models import Symbol


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
