from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_simplify_legacy_substrate"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="termsymbol",
            index=models.Index(
                fields=["order", "symbol", "term"],
                name="core_ts_ord_sym_term_idx",
            ),
        ),
    ]
