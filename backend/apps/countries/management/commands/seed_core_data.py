from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.countries.models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    Country,
    CountryCorridor,
    Currency,
    PayoutProvider,
)
from apps.quotes.models import ExchangeRate, FeeRule
from common.choices import PayoutMethod


class Command(BaseCommand):
    help = "Seed core currencies, countries, corridors, rates, and fee rules."

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
        PayoutMethod.MOBILE_MONEY: {
            "fixed_fee": Decimal("2.99"),
            "percentage_fee": Decimal("1.50"),
        },
        PayoutMethod.BANK_DEPOSIT: {
            "fixed_fee": Decimal("4.99"),
            "percentage_fee": Decimal("1.00"),
        },
    }

    PAYOUT_PROVIDER_DEFAULTS = {
        PayoutMethod.MOBILE_MONEY: {
            "code": "mtn_momo",
            "name": "MTN MoMo",
            "metadata": {
                "processor": "mtn_momo",
            },
        },
        PayoutMethod.BANK_DEPOSIT: {
            "code": "internal_bank_deposit",
            "name": "Internal bank deposit operations",
            "metadata": {},
        },
    }

    @transaction.atomic
    def handle(self, *args, **options):
        currencies = self.seed_currencies()
        countries = self.seed_countries(currencies)
        corridors = self.seed_corridors(countries)
        self.seed_exchange_rates(corridors)
        self.seed_fee_rules(corridors)
        providers = self.seed_payout_providers()
        self.seed_corridor_payout_routes(corridors, providers)

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

    def seed_corridors(
        self,
        countries: dict[str, Country],
    ) -> dict[tuple[str, str], tuple[CountryCorridor, Decimal]]:
        corridors = {}

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
            corridors[
                (source_country.iso_code, destination_country.iso_code)
            ] = (corridor, item["exchange_rate"])
            self.stdout.write(f"Seeded corridor: {corridor}")

        return corridors

    def seed_exchange_rates(
        self,
        corridors: dict[tuple[str, str], tuple[CountryCorridor, Decimal]],
    ) -> None:
        now = timezone.now()

        for corridor, exchange_rate in corridors.values():
            rate, _ = ExchangeRate.objects.update_or_create(
                corridor=corridor,
                provider_name="seeded_mid_market",
                is_active=True,
                defaults={
                    "rate": exchange_rate,
                    "effective_at": now,
                    "expires_at": None,
                },
            )
            self.stdout.write(f"Seeded exchange rate: {rate}")

    def seed_fee_rules(
        self,
        corridors: dict[tuple[str, str], tuple[CountryCorridor, Decimal]],
    ) -> None:
        for corridor, _exchange_rate in corridors.values():
            for payout_method, defaults in self.PAYOUT_FEE_DEFAULTS.items():
                fee_rule, _ = FeeRule.objects.update_or_create(
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
                self.stdout.write(f"Seeded fee rule: {fee_rule}")

    def seed_payout_providers(self) -> dict[str, PayoutProvider]:
        providers = {}

        for payout_method, item in self.PAYOUT_PROVIDER_DEFAULTS.items():
            provider, _ = PayoutProvider.objects.update_or_create(
                code=item["code"],
                defaults={
                    "name": item["name"],
                    "payout_method": payout_method,
                    "is_active": True,
                    "metadata": item.get("metadata", {}),
                },
            )
            providers[payout_method] = provider
            self.stdout.write(f"Seeded payout provider: {provider}")

        return providers

    def seed_corridor_payout_routes(
        self,
        corridors: dict[tuple[str, str], tuple[CountryCorridor, Decimal]],
        providers: dict[str, PayoutProvider],
    ) -> None:
        for corridor, _exchange_rate in corridors.values():
            for payout_method, provider in providers.items():
                route, _ = CorridorPayoutMethod.objects.update_or_create(
                    corridor=corridor,
                    payout_method=payout_method,
                    defaults={
                        "is_active": True,
                        "min_send_amount": None,
                        "max_send_amount": None,
                        "display_order": 10
                        if payout_method == PayoutMethod.MOBILE_MONEY
                        else 20,
                    },
                )
                provider_route, _ = CorridorPayoutProvider.objects.update_or_create(
                    corridor_payout_method=route,
                    provider=provider,
                    defaults={
                        "is_active": True,
                        "priority": 10,
                        "min_send_amount": None,
                        "max_send_amount": None,
                    },
                )
                self.stdout.write(f"Seeded payout route: {provider_route}")
