from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.countries.models import Country, CountryCorridor, Currency


class Command(BaseCommand):
    help = "Seed core currencies, countries, and Zambia payout corridors."

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
        },
        {
            "source_iso_code": "GB",
            "destination_iso_code": "ZM",
            "min_send_amount": Decimal("10.00"),
            "max_send_amount": Decimal("5000.00"),
        },
        {
            "source_iso_code": "DE",
            "destination_iso_code": "ZM",
            "min_send_amount": Decimal("10.00"),
            "max_send_amount": Decimal("5000.00"),
        },
    ]

    @transaction.atomic
    def handle(self, *args, **options):
        currencies = self.seed_currencies()
        countries = self.seed_countries(currencies)
        self.seed_corridors(countries)

        self.stdout.write(self.style.SUCCESS("Core remittance seed data is ready."))

    def seed_currencies(self) -> dict[str, Currency]:
        currencies = {}

        for item in self.CURRENCIES:
            currency, _ = Currency.objects.update_or_create(
                code=item["code"],
                defaults={
                    "name": item["name"],
                    "minor_unit": item["minor_unit"],
                },
            )
            currencies[currency.code] = currency
            self.stdout.write(f"Seeded currency: {currency.code}")

        return currencies

    def seed_countries(self, currencies: dict[str, Currency]) -> dict[str, Country]:
        countries = {}

        for item in self.COUNTRIES:
            currency = currencies[item["currency_code"]]
            country, _ = Country.objects.update_or_create(
                iso_code=item["iso_code"],
                defaults={
                    "name": item["name"],
                    "dialing_code": item["dialing_code"],
                    "currency": currency,
                    "is_sender_enabled": item["is_sender_enabled"],
                    "is_destination_enabled": item["is_destination_enabled"],
                },
            )
            countries[country.iso_code] = country
            self.stdout.write(f"Seeded country: {country.name}")

        return countries

    def seed_corridors(self, countries: dict[str, Country]) -> None:
        for item in self.CORRIDORS:
            source_country = countries[item["source_iso_code"]]
            destination_country = countries[item["destination_iso_code"]]

            corridor, _ = CountryCorridor.objects.update_or_create(
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
            self.stdout.write(f"Seeded corridor: {corridor}")
