from decimal import Decimal

from django.db import migrations
from django.utils import timezone


CURRENCIES = [
    {"code": "USD", "name": "US Dollar", "minor_unit": 2},
    {"code": "GBP", "name": "British Pound", "minor_unit": 2},
    {"code": "EUR", "name": "Euro", "minor_unit": 2},
    {"code": "ZMW", "name": "Zambian Kwacha", "minor_unit": 2},
]

COUNTRIES = [
    {
        "iso_code": "US",
        "name": "United States",
        "dialing_code": "+1",
        "currency_code": "USD",
        "is_sender_enabled": True,
        "is_destination_enabled": False,
    },
    {
        "iso_code": "GB",
        "name": "United Kingdom",
        "dialing_code": "+44",
        "currency_code": "GBP",
        "is_sender_enabled": True,
        "is_destination_enabled": False,
    },
    {
        "iso_code": "DE",
        "name": "Germany",
        "dialing_code": "+49",
        "currency_code": "EUR",
        "is_sender_enabled": True,
        "is_destination_enabled": False,
    },
    {
        "iso_code": "ZM",
        "name": "Zambia",
        "dialing_code": "+260",
        "currency_code": "ZMW",
        "is_sender_enabled": False,
        "is_destination_enabled": True,
    },
]

CORRIDORS = [
    {
        "source_iso_code": "US",
        "destination_iso_code": "ZM",
        "min_send_amount": Decimal("10.00"),
        "max_send_amount": Decimal("5000.00"),
        "exchange_rate": Decimal("25.50000000"),
    },
    {
        "source_iso_code": "GB",
        "destination_iso_code": "ZM",
        "min_send_amount": Decimal("10.00"),
        "max_send_amount": Decimal("5000.00"),
        "exchange_rate": Decimal("32.25000000"),
    },
    {
        "source_iso_code": "DE",
        "destination_iso_code": "ZM",
        "min_send_amount": Decimal("10.00"),
        "max_send_amount": Decimal("5000.00"),
        "exchange_rate": Decimal("27.40000000"),
    },
]

PAYOUT_FEE_DEFAULTS = {
    "mobile_money": {
        "fixed_fee": Decimal("2.99"),
        "percentage_fee": Decimal("1.50"),
        "display_order": 10,
    },
    "bank_deposit": {
        "fixed_fee": Decimal("4.99"),
        "percentage_fee": Decimal("1.00"),
        "display_order": 20,
    },
}

PAYOUT_PROVIDER_DEFAULTS = {
    "mobile_money": {
        "code": "mtn_momo",
        "name": "MTN MoMo",
        "priority": 5,
        "metadata": {
            "processor": "mtn_momo",
        },
    },
    "bank_deposit": {
        "code": "internal_bank_deposit",
        "name": "Internal bank deposit operations",
        "priority": 10,
        "metadata": {},
    },
}


def backfill_supported_route_data(apps, schema_editor):
    database_name = str(schema_editor.connection.settings_dict.get("NAME") or "")
    if database_name.startswith("test_"):
        return

    currency_model = apps.get_model("countries", "Currency")
    country_model = apps.get_model("countries", "Country")
    country_corridor_model = apps.get_model("countries", "CountryCorridor")
    payout_provider_model = apps.get_model("countries", "PayoutProvider")
    corridor_payout_method_model = apps.get_model("countries", "CorridorPayoutMethod")
    corridor_payout_provider_model = apps.get_model(
        "countries",
        "CorridorPayoutProvider",
    )
    exchange_rate_model = apps.get_model("quotes", "ExchangeRate")
    fee_rule_model = apps.get_model("quotes", "FeeRule")

    currencies = {}
    for item in CURRENCIES:
        currency, _ = currency_model.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "minor_unit": item["minor_unit"],
            },
        )
        currencies[currency.code] = currency

    countries = {}
    for item in COUNTRIES:
        country, _ = country_model.objects.update_or_create(
            iso_code=item["iso_code"],
            defaults={
                "name": item["name"],
                "dialing_code": item["dialing_code"],
                "currency": currencies[item["currency_code"]],
                "is_sender_enabled": item["is_sender_enabled"],
                "is_destination_enabled": item["is_destination_enabled"],
            },
        )
        countries[country.iso_code] = country

    providers = {}
    for payout_method, item in PAYOUT_PROVIDER_DEFAULTS.items():
        provider, _ = payout_provider_model.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "payout_method": payout_method,
                "is_active": True,
                "metadata": item["metadata"],
            },
        )
        providers[payout_method] = provider

    now = timezone.now()
    for item in CORRIDORS:
        source_country = countries[item["source_iso_code"]]
        destination_country = countries[item["destination_iso_code"]]
        corridor, _ = country_corridor_model.objects.update_or_create(
            source_country=source_country,
            destination_country=destination_country,
            defaults={
                "source_currency": source_country.currency,
                "destination_currency": destination_country.currency,
                "is_active": True,
                "min_send_amount": item["min_send_amount"],
                "max_send_amount": item["max_send_amount"],
            },
        )
        exchange_rate_model.objects.update_or_create(
            corridor=corridor,
            provider_name="seeded_mid_market",
            is_active=True,
            defaults={
                "rate": item["exchange_rate"],
                "effective_at": now,
                "expires_at": None,
            },
        )

        for payout_method, defaults in PAYOUT_FEE_DEFAULTS.items():
            fee_rule_model.objects.update_or_create(
                corridor=corridor,
                payout_method=payout_method,
                min_amount=corridor.min_send_amount,
                max_amount=corridor.max_send_amount,
                defaults={
                    "fixed_fee": defaults["fixed_fee"],
                    "percentage_fee": defaults["percentage_fee"],
                    "is_active": True,
                },
            )
            payout_method_route, _ = corridor_payout_method_model.objects.update_or_create(
                corridor=corridor,
                payout_method=payout_method,
                defaults={
                    "is_active": True,
                    "min_send_amount": None,
                    "max_send_amount": None,
                    "display_order": defaults["display_order"],
                },
            )
            provider = providers[payout_method]
            provider_defaults = PAYOUT_PROVIDER_DEFAULTS[payout_method]
            corridor_payout_provider_model.objects.update_or_create(
                corridor_payout_method=payout_method_route,
                provider=provider,
                defaults={
                    "is_active": True,
                    "priority": provider_defaults["priority"],
                    "min_send_amount": None,
                    "max_send_amount": None,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ("countries", "0003_corridorpayoutmethod_payoutprovider_and_more"),
        ("quotes", "0005_seed_default_exchange_rates"),
    ]

    operations = [
        migrations.RunPython(
            backfill_supported_route_data,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
