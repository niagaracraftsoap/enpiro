from django.db import migrations, models


ENVIRONMENT_SCHEMA = b"enpiro.environment.v1"
LOCAL_SOURCE_ID = b"local"


def add_local_source_to_environment_terms(apps, schema_editor):
    """Replace the unnecessary marker with the local source Symbol."""
    Term = apps.get_model("core", "Term")
    Symbol = apps.get_model("core", "Symbol")
    TermSymbol = apps.get_model("core", "TermSymbol")

    source_symbol = None
    terms = (
        Term.objects.annotate(_symbol_count=models.Count("termsymbol"))
        .filter(_symbol_count=5)
        .iterator(chunk_size=500)
    )
    for term in terms:
        relations = list(
            TermSymbol.objects.filter(term_id=term.pk)
            .select_related("symbol")
            .order_by("order")
        )
        atoms = [bytes(relation.symbol.symbol) for relation in relations]
        if atoms[0] != ENVIRONMENT_SCHEMA:
            continue

        if source_symbol is None:
            source_symbol, _created = Symbol.objects.get_or_create(
                symbol=LOCAL_SOURCE_ID
            )

        marker = relations[0]
        marker.symbol_id = source_symbol.pk
        marker.save(update_fields=["symbol"])


class Migration(migrations.Migration):
    dependencies = [("measurements", "0004_mark_unconverted_environment_terms")]

    operations = [
        migrations.RunPython(
            add_local_source_to_environment_terms,
            migrations.RunPython.noop,
        ),
    ]
