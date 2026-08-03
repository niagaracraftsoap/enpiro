"""Shared clear Term/Symbol storage substrate."""

from django.core.validators import MaxLengthValidator
from django.db import models


class SymbolManager(models.Manager):
    def resolve_clear(self, value):
        symbol, _created = self.get_or_create(symbol=bytes(value))
        return symbol


class Symbol(models.Model):
    symbol = models.BinaryField(
        max_length=65_535,
        validators=[MaxLengthValidator(65_535)],
        editable=False,
        db_index=True,
    )
    objects = SymbolManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["symbol"],
                name="unique_inline_symbol",
            )
        ]

    def __bytes__(self):
        return bytes(self.symbol)

    def __str__(self):
        return self.symbol.decode("utf-8", errors="replace")


class Term(models.Model):
    def __str__(self):
        parts = []
        remaining = 256
        for relation in self.termsymbol_set.select_related("symbol").order_by("order"):
            symbol = relation.symbol
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["term", "order"],
                name="unique_symbol_order_per_term",
            )
        ]
        ordering = ["order"]
