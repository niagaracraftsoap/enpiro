from django.test import TestCase

from .models import RootKey, Symbol, SystemKey


class SubstrateTests(TestCase):
    def test_clear_symbols_are_shared(self):
        first = Symbol.objects.resolve_clear(b"temperature_c")
        second = Symbol.objects.resolve_clear(b"temperature_c")
        self.assertEqual(first.pk, second.pk)

    def test_system_key_encryption_round_trip(self):
        key = SystemKey.objects.create(root_key=RootKey.objects.current)
        ciphertext = key.encrypt(b"environmental secret")
        self.assertEqual(key.decrypt(ciphertext), b"environmental secret")
