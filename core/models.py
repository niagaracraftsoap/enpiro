"""Shared clear Term/Symbol storage substrate."""

from django.core.validators import MaxLengthValidator
from django.db import models, transaction
from django.db.models import Count


def _coerce_blob_sequence(value_or_values):
    """Normalize one binary blob or an ordered iterable of blobs."""
    if isinstance(value_or_values, (bytes, bytearray, memoryview)):
        values = (value_or_values,)
    else:
        try:
            values = tuple(value_or_values)
        except TypeError as error:
            raise TypeError(
                "expected a binary blob or an iterable of binary blobs"
            ) from error

    if not values:
        raise ValueError("a Term must contain at least one Symbol")

    try:
        return tuple(bytes(value) for value in values)
    except (TypeError, ValueError) as error:
        raise TypeError(
            "expected a binary blob or an iterable of binary blobs"
        ) from error


class SymbolManager(models.Manager):
    def resolve_clear_many(self, values):
        """Resolve an ordered batch of binary values to deduplicated Symbols."""
        blobs = _coerce_blob_sequence(values)
        unique_blobs = tuple(dict.fromkeys(blobs))
        def existing_by_blob():
            return {
                bytes(symbol.symbol): symbol
                for symbol in self.filter(symbol__in=unique_blobs)
            }

        existing = existing_by_blob()
        missing = tuple(
            blob for blob in unique_blobs if blob not in existing
        )

        if missing:
            self.bulk_create(
                [self.model(symbol=blob) for blob in missing],
                ignore_conflicts=True,
            )
            # Re-read after bulk creation because ignored inserts do not
            # reliably populate primary keys across database backends.
            existing = existing_by_blob()

        return (
            tuple(existing[blob] for blob in blobs),
            bool(missing),
        )

    def resolve_clear(self, value):
        """Resolve one binary value to its deduplicated Symbol."""
        symbols, _created = self.resolve_clear_many((value,))
        return symbols[0]


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


class TermManager(models.Manager):
    def _find_exact(self, symbols):
        queryset = self.get_queryset()
        for order, symbol in enumerate(symbols):
            queryset = queryset.filter(
                termsymbol__order=order,
                termsymbol__symbol_id=symbol.pk,
            )
        return (
            queryset.annotate(
                _symbol_count=Count("termsymbol", distinct=True)
            )
            .filter(_symbol_count=len(symbols))
            .first()
        )

    def resolve_clear(self, value_or_values):
        """Resolve one blob or an ordered iterable of blobs to a Term."""
        blobs = _coerce_blob_sequence(value_or_values)

        with transaction.atomic():
            symbols, any_created = Symbol.objects.resolve_clear_many(blobs)

            # If a Symbol was novel, an identical Term could not already have
            # existed. When all Symbols already exist, reuse an exact ordered
            # Term if one is present.
            if not any_created:
                existing = self._find_exact(symbols)
                if existing is not None:
                    return existing

            term = self.create()
            TermSymbol.objects.bulk_create(
                [
                    TermSymbol(term=term, symbol=symbol, order=order)
                    for order, symbol in enumerate(symbols)
                ]
            )
            return term


class Term(models.Model):
    objects = TermManager()

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
