from decimal import Decimal

from django.db import migrations
from django.utils import timezone


DEFAULT_EXCHANGE_RATES = {
    ("US", "ZM"): Decimal("25.50000000"),
    ("GB", "ZM"): Decimal("32.25000000"),
    ("DE", "ZM"): Decimal("27.40000000"),
}


def seed_default_exchange_rates(apps, schema_editor):
    country_corridor_model = apps.get_model("countries", "CountryCorridor")
    exchange_rate_model = apps.get_model("quotes", "ExchangeRate")
    now = timezone.now()

    corridors = country_corridor_model.objects.select_related(
        "source_country",
        "destination_country",
    ).filter(
        source_country__iso_code__in=[source for source, _ in DEFAULT_EXCHANGE_RATES],
        destination_country__iso_code__in=[
            destination for _, destination in DEFAULT_EXCHANGE_RATES
        ],
    )

    for corridor in corridors:
        route_key = (
            corridor.source_country.iso_code,
            corridor.destination_country.iso_code,
        )
        exchange_rate = DEFAULT_EXCHANGE_RATES.get(route_key)
        if exchange_rate is None:
            continue

        exchange_rate_model.objects.update_or_create(
            corridor=corridor,
            provider_name="seeded_mid_market",
            is_active=True,
            defaults={
                "rate": exchange_rate,
                "effective_at": now,
                "expires_at": None,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("countries", "0003_corridorpayoutmethod_payoutprovider_and_more"),
        ("quotes", "0004_quote_fx_metadata"),
    ]

    operations = [
        migrations.RunPython(
            seed_default_exchange_rates,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
