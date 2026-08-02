import struct
from datetime import datetime, timedelta, timezone

from django.db import migrations, models
import django.db.models.deletion


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def populate_index(apps, schema_editor):
    Term = apps.get_model("core", "Term")
    QuickCheckIndex = apps.get_model("measurements", "QuickCheckIndex")
    terms = Term.objects.annotate(
        symbol_count=models.Count("termsymbol")
    ).filter(symbol_count=4)
    indexes = []
    for term in terms.iterator(chunk_size=500):
        atoms = list(
            term.termsymbol_set.select_related("symbol")
            .order_by("order")
            .values_list("symbol__symbol", flat=True)
        )
        if [len(atom) for atom in atoms] != [8, 2, 2, 2]:
            continue
        try:
            observed_at = EPOCH + timedelta(
                microseconds=struct.unpack(">q", bytes(atoms[0]))[0]
            )
            temperature_c = struct.unpack(">h", bytes(atoms[1]))[0] / 10
            pressure_hpa = float(struct.unpack(">H", bytes(atoms[2]))[0])
            relative_humidity = struct.unpack(">H", bytes(atoms[3]))[0] / 10
        except (OverflowError, struct.error):
            continue
        indexes.append(QuickCheckIndex(
            term_id=term.pk,
            observed_at=observed_at,
            temperature_c=temperature_c,
            relative_humidity=relative_humidity,
            pressure_hpa=pressure_hpa,
        ))
        if len(indexes) == 500:
            QuickCheckIndex.objects.bulk_create(indexes)
            indexes.clear()
    QuickCheckIndex.objects.bulk_create(indexes)


class Migration(migrations.Migration):
    dependencies = [("measurements", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="QuickCheckIndex",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("observed_at", models.DateTimeField(db_index=True)),
                ("temperature_c", models.FloatField()),
                ("relative_humidity", models.FloatField()),
                ("pressure_hpa", models.FloatField()),
                ("term", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="quick_check_index", to="core.term")),
            ],
            options={"ordering": ["observed_at"]},
        ),
        migrations.RunPython(populate_index, migrations.RunPython.noop),
    ]
