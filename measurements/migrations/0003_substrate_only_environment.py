from django.db import migrations, models


ENVIRONMENT_SCHEMA = b"enpiro.environment.v1"


def mark_existing_environment_terms(apps, schema_editor):
    """Add the semantic marker to observations written by the old path."""
    Term = apps.get_model("core", "Term")
    Symbol = apps.get_model("core", "Symbol")
    TermSymbol = apps.get_model("core", "TermSymbol")

    terms = list(
        Term.objects.annotate(_symbol_count=models.Count("termsymbol"))
        .filter(_symbol_count=4)
    )
    schema_symbol = None
    for term in terms:
        relations = list(
            TermSymbol.objects.filter(term_id=term.pk)
            .select_related("symbol")
            .order_by("order")
        )
        atoms = [bytes(relation.symbol.symbol) for relation in relations]
        if [len(atom) for atom in atoms] not in ([8, 2, 2, 2], [8, 2, 4, 2]):
            continue

        if schema_symbol is None:
            schema_symbol, _created = Symbol.objects.get_or_create(
                symbol=ENVIRONMENT_SCHEMA
            )

        # Move the existing positions out of the way before inserting order 0.
        for relation in relations:
            relation.order += 10
            relation.save(update_fields=["order"])
        for relation in relations:
            relation.order -= 9
            relation.save(update_fields=["order"])
        TermSymbol.objects.create(
            term_id=term.pk,
            symbol_id=schema_symbol.pk,
            order=0,
        )


class Migration(migrations.Migration):
    dependencies = [("measurements", "0002_quickcheckindex")]

    operations = [
        migrations.RunPython(
            mark_existing_environment_terms,
            migrations.RunPython.noop,
        ),
        migrations.DeleteModel(name="QuickCheckIndex"),
        migrations.DeleteModel(name="QuickCheck"),
    ]
