from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("transfers", "0018_transfernotification"),
    ]

    operations = [
        migrations.AddField(
            model_name="transfer",
            name="is_live_rate",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="transfer",
            name="is_primary_rate",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="transfer",
            name="rate_provider_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="transfer",
            name="rate_source",
            field=models.CharField(default="database", max_length=40),
        ),
    ]
