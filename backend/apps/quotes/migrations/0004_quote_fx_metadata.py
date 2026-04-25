from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quotes", "0003_exchangerate"),
    ]

    operations = [
        migrations.AddField(
            model_name="quote",
            name="is_live_rate",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="quote",
            name="is_primary_rate",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="quote",
            name="rate_provider_name",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="quote",
            name="rate_source",
            field=models.CharField(default="database", max_length=40),
        ),
    ]
