from django.db import migrations


LEGACY_TABLES = (
    "legacy_core_termsymbol",
    "legacy_core_symbol",
    "legacy_core_term",
)


def table_names(connection):
    return set(connection.introspection.table_names())


def column_names(connection, table):
    with connection.cursor() as cursor:
        return {
            column.name
            for column in connection.introspection.get_table_description(cursor, table)
        }


def simplify_legacy_substrate(apps, schema_editor):
    """Converge the older encrypted-capable schema on the production schema."""
    connection = schema_editor.connection
    tables = table_names(connection)
    if "created_at" not in column_names(connection, "core_symbol"):
        return
    if connection.vendor != "sqlite":
        raise RuntimeError("The legacy Enpiro substrate upgrade currently supports SQLite only.")
    if set(LEGACY_TABLES) & tables:
        raise RuntimeError("A previous legacy substrate upgrade did not finish cleanly.")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM core_symbol
            WHERE system_key_id IS NOT NULL
               OR COALESCE(file, '') <> ''
               OR symbol IS NULL
            """
        )
        unsupported_symbols = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM core_termsymbol WHERE mutation_id IS NOT NULL")
        mutations = cursor.fetchone()[0]
    if unsupported_symbols or mutations:
        raise RuntimeError(
            "Cannot simplify a substrate containing encrypted/file symbols or mutations."
        )

    Term = apps.get_model("core", "Term")
    Symbol = apps.get_model("core", "Symbol")
    TermSymbol = apps.get_model("core", "TermSymbol")
    with connection.constraint_checks_disabled():
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE core_termsymbol RENAME TO legacy_core_termsymbol")
            cursor.execute("ALTER TABLE core_symbol RENAME TO legacy_core_symbol")
            cursor.execute("ALTER TABLE core_term RENAME TO legacy_core_term")

        schema_editor.create_model(Term)
        schema_editor.create_model(Symbol)
        schema_editor.create_model(TermSymbol)

        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO core_term (id) SELECT id FROM legacy_core_term")
            cursor.execute(
                "INSERT INTO core_symbol (id, symbol) "
                "SELECT id, symbol FROM legacy_core_symbol"
            )
            cursor.execute(
                "INSERT INTO core_termsymbol (id, `order`, symbol_id, term_id) "
                "SELECT id, `order`, symbol_id, term_id FROM legacy_core_termsymbol"
            )
            cursor.execute("DROP TABLE legacy_core_termsymbol")
            cursor.execute("DROP TABLE legacy_core_symbol")
            cursor.execute("DROP TABLE legacy_core_term")
            cursor.execute("DROP TABLE IF EXISTS core_systemkey")
            cursor.execute("DROP TABLE IF EXISTS core_rootkey")

    connection.check_constraints()


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(simplify_legacy_substrate, migrations.RunPython.noop)]
