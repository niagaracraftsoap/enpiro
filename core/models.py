"""Shared Term/Symbol storage substrate, ported from artofbodhi/core/models.py."""

import base64
from os import urandom
from datetime import timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils import timezone


def rnd32():
    return urandom(32)


class Timestamp(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class RootKeyManager(models.Manager):
    @property
    def current(self):
        try:
            latest = self.latest("created_at")
        except self.model.DoesNotExist:
            return self.create()
        rotation_seconds = getattr(settings, "ROOT_KEY_ROTATION_SECONDS", 2_592_000)
        if timezone.now() - latest.created_at >= timedelta(seconds=rotation_seconds):
            return self.create()
        return latest


class RootKey(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    salt = models.BinaryField(default=rnd32, editable=False)

    objects = RootKeyManager()

    @property
    def key_bytes(self):
        try:
            anchor = base64.b64decode(settings.ANCHOR, validate=True)
        except (AttributeError, ValueError) as error:
            raise ImproperlyConfigured(
                "ANCHOR must be a base64-encoded secret for encrypted symbols."
            ) from error
        return HKDF(
            algorithm=hashes.BLAKE2b(64),
            length=32,
            salt=self.salt,
            info=self.created_at.isoformat().encode(),
        ).derive(anchor)

    def __str__(self):
        return f"RootKey {self.pk}"


class SystemKey(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    salt = models.BinaryField(default=rnd32, editable=False)
    root_key = models.ForeignKey(
        RootKey,
        null=True,
        on_delete=models.PROTECT,
        related_name="system_keys",
    )

    @property
    def resolved_root_key(self):
        if self.root_key_id:
            return self.root_key
        historical = RootKey.objects.filter(created_at__lte=self.created_at).last()
        return historical or RootKey.objects.current

    @property
    def key_bytes(self):
        return HKDF(
            algorithm=hashes.BLAKE2b(64),
            length=32,
            salt=self.salt,
            info=self.created_at.isoformat().encode(),
        ).derive(self.resolved_root_key.key_bytes)

    def encrypt(self, plain_bytes):
        iv = urandom(12)
        ciphertext = AESGCM(self.key_bytes).encrypt(
            iv,
            plain_bytes,
            self.created_at.isoformat().encode(),
        )
        return iv + ciphertext

    def decrypt(self, ciphertext):
        iv, payload = ciphertext[:12], ciphertext[12:]
        return AESGCM(self.key_bytes).decrypt(
            iv,
            payload,
            self.created_at.isoformat().encode(),
        )

    def __str__(self):
        return f"SystemKey {self.pk}"


class SymbolManager(models.Manager):
    def resolve_clear(self, value):
        symbol, _created = self.get_or_create(
            symbol=bytes(value),
            system_key=None,
            defaults={"file": None},
        )
        return symbol

    def create_encrypted(self, value):
        system_key = SystemKey.objects.create(root_key=RootKey.objects.current)
        return self.create(system_key=system_key, symbol=system_key.encrypt(bytes(value)))


class Symbol(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    symbol = models.BinaryField(
        max_length=65_535,
        validators=[MaxLengthValidator(65_535)],
        editable=False,
        null=True,
        db_index=True,
    )
    file = models.FileField(
        upload_to="symbol/",
        editable=False,
        max_length=255,
        null=True,
        db_index=True,
    )
    system_key = models.ForeignKey(
        SystemKey,
        null=True,
        on_delete=models.CASCADE,
        related_name="symbols",
    )

    objects = SymbolManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol"],
                condition=models.Q(system_key__isnull=True, symbol__isnull=False),
                name="unique_clear_inline_symbol",
            )
        ]

    def __bytes__(self):
        return bytes(self.symbol or b"")

    def __str__(self):
        if self.system_key_id:
            return "EncryptedSymbol"
        if self.symbol is not None:
            return self.symbol.decode("utf-8", errors="replace")
        return self.file.name if self.file else "EmptySymbol"


class Term(Timestamp):
    def __str__(self):
        parts = []
        remaining = 256
        for relation in self.termsymbol_set.select_related("symbol").order_by("order"):
            symbol = relation.symbol
            if symbol.system_key_id:
                return "EncryptedTerm"
            if symbol.symbol is None:
                return "FileTerm" if symbol.file else "InvalidTerm"
            text = symbol.symbol.decode("utf-8", errors="replace")
            parts.append(text[:remaining])
            remaining -= len(text)
            if remaining <= 0:
                return "".join(parts) + "…"
        return "".join(parts)


class TermSymbol(models.Model):
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    symbol = models.ForeignKey(Symbol, on_delete=models.PROTECT)
    order = models.PositiveIntegerField()
    mutation = models.ForeignKey(
        Symbol,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="term_symbol_mutations",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["term", "order"],
                name="unique_symbol_order_per_term",
            )
        ]
        ordering = ["order"]

