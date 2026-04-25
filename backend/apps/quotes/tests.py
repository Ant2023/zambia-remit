from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.countries.models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    Country,
    CountryCorridor,
    Currency,
    PayoutProvider,
)
from common.choices import PayoutMethod
from common.integrations import ProviderRequestError

from .models import ExchangeRate, FeeRule, Quote


User = get_user_model()


@override_settings(FX_RATE_SOURCE="database", FX_RATE_SOURCE_CONFIGS={})
class QuotePayoutRouteTests(APITestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar")
        self.zmw = Currency.objects.create(code="ZMW", name="Zambian Kwacha")
        self.us = Country.objects.create(
            name="United States",
            iso_code="US",
            dialing_code="+1",
            currency=self.usd,
            is_sender_enabled=True,
        )
        self.zambia = Country.objects.create(
            name="Zambia",
            iso_code="ZM",
            dialing_code="+260",
            currency=self.zmw,
            is_destination_enabled=True,
        )
        self.corridor = CountryCorridor.objects.create(
            source_country=self.us,
            destination_country=self.zambia,
            source_currency=self.usd,
            destination_currency=self.zmw,
            min_send_amount=Decimal("10.00"),
            max_send_amount=Decimal("5000.00"),
        )
        ExchangeRate.objects.create(
            corridor=self.corridor,
            rate=Decimal("25.50000000"),
            provider_name="test_rate",
            effective_at=timezone.now(),
        )
        FeeRule.objects.create(
            corridor=self.corridor,
            payout_method=PayoutMethod.MOBILE_MONEY,
            min_amount=Decimal("10.00"),
            max_amount=Decimal("5000.00"),
            fixed_fee=Decimal("2.99"),
            percentage_fee=Decimal("1.50"),
        )
        provider = PayoutProvider.objects.create(
            code="test_quote_mobile_money",
            name="Test quote mobile money",
            payout_method=PayoutMethod.MOBILE_MONEY,
        )
        route = CorridorPayoutMethod.objects.create(
            corridor=self.corridor,
            payout_method=PayoutMethod.MOBILE_MONEY,
        )
        CorridorPayoutProvider.objects.create(
            corridor_payout_method=route,
            provider=provider,
        )
        self.sender = User.objects.create_user(
            email="quote-route@example.com",
            password="test-password-123",
        )

    def test_quote_creation_uses_corridor_payout_route_availability(self):
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("quote-list-create"),
            {
                "corridor_id": str(self.corridor.id),
                "payout_method": PayoutMethod.MOBILE_MONEY,
                "send_amount": "100.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        quote = Quote.objects.get(id=response.data["id"])
        self.assertEqual(quote.payout_method, PayoutMethod.MOBILE_MONEY)
        self.assertEqual(quote.rate_source, "database")
        self.assertEqual(quote.rate_provider_name, "test_rate")
        self.assertTrue(quote.is_primary_rate)
        self.assertFalse(quote.is_live_rate)

    def test_quote_creation_rejects_payout_method_without_corridor_route(self):
        self.client.force_authenticate(self.sender)

        response = self.client.post(
            reverse("quote-list-create"),
            {
                "corridor_id": str(self.corridor.id),
                "payout_method": PayoutMethod.BANK_DEPOSIT,
                "send_amount": "100.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not available", str(response.data["payout_method"]))

    @override_settings(
        FX_RATE_SOURCE="open_exchange_rates",
        FX_RATE_SOURCE_CONFIGS={
            "open_exchange_rates": {
                "app_id": "test-app-id",
                "use_symbols": True,
            },
        },
    )
    @patch("apps.quotes.fx_sources.request_json")
    def test_quote_creation_preserves_live_fx_metadata(self, mock_request_json):
        self.client.force_authenticate(self.sender)
        mock_request_json.return_value = {
            "base": "USD",
            "timestamp": 1776834000,
            "rates": {
                "ZMW": "25.50000000",
            },
        }

        response = self.client.post(
            reverse("quote-list-create"),
            {
                "corridor_id": str(self.corridor.id),
                "payout_method": PayoutMethod.MOBILE_MONEY,
                "send_amount": "100.00",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["rate_source"], "open_exchange_rates")
        self.assertEqual(response.data["rate_provider_name"], "open_exchange_rates")
        self.assertTrue(response.data["is_primary_rate"])
        self.assertTrue(response.data["is_live_rate"])

        quote = Quote.objects.get(id=response.data["id"])
        self.assertEqual(quote.rate_source, "open_exchange_rates")
        self.assertEqual(quote.rate_provider_name, "open_exchange_rates")
        self.assertTrue(quote.is_primary_rate)
        self.assertTrue(quote.is_live_rate)

    @override_settings(
        FX_RATE_SOURCE="open_exchange_rates",
        FX_RATE_SOURCE_CONFIGS={
            "open_exchange_rates": {
                "app_id": "test-app-id",
                "use_symbols": True,
            },
        },
    )
    @patch("apps.quotes.fx_sources.request_json")
    def test_rate_estimate_uses_open_exchange_rates(self, mock_request_json):
        mock_request_json.return_value = {
            "base": "USD",
            "timestamp": 1776834000,
            "rates": {
                "ZMW": "25.50000000",
            },
        }

        response = self.client.get(
            reverse("rate-estimate"),
            {
                "source_country_id": str(self.us.id),
                "destination_country_id": str(self.zambia.id),
                "send_amount": "100.00",
                "payout_method": PayoutMethod.MOBILE_MONEY,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["exchange_rate"]), "25.50000000")
        self.assertEqual(str(response.data["receive_amount"]), "2550.00")
        self.assertEqual(response.data["rate_source"], "open_exchange_rates")
        self.assertEqual(response.data["rate_provider_name"], "open_exchange_rates")
        self.assertTrue(response.data["is_primary_rate"])
        self.assertTrue(response.data["is_live_rate"])
        request_kwargs = mock_request_json.call_args.kwargs
        self.assertEqual(request_kwargs["method"], "GET")
        self.assertFalse(request_kwargs["include_api_key_auth"])
        self.assertIn("/latest.json?", request_kwargs["path"])
        self.assertIn("app_id=test-app-id", request_kwargs["path"])
        self.assertIn("symbols=USD%2CZMW", request_kwargs["path"])

    @override_settings(
        FX_RATE_SOURCE="open_exchange_rates",
        FX_RATE_SOURCE_CONFIGS={
            "open_exchange_rates": {
                "api_key": "test-app-id",
            },
        },
    )
    @patch("apps.quotes.fx_sources.request_json")
    def test_open_exchange_rates_supports_cross_currency_rates(
        self,
        mock_request_json,
    ):
        gbp = Currency.objects.create(code="GBP", name="British Pound")
        uk = Country.objects.create(
            name="United Kingdom",
            iso_code="GB",
            dialing_code="+44",
            currency=gbp,
            is_sender_enabled=True,
        )
        gbp_corridor = CountryCorridor.objects.create(
            source_country=uk,
            destination_country=self.zambia,
            source_currency=gbp,
            destination_currency=self.zmw,
            min_send_amount=Decimal("10.00"),
            max_send_amount=Decimal("5000.00"),
        )
        route = CorridorPayoutMethod.objects.create(
            corridor=gbp_corridor,
            payout_method=PayoutMethod.MOBILE_MONEY,
        )
        provider = PayoutProvider.objects.get(code="test_quote_mobile_money")
        CorridorPayoutProvider.objects.create(
            corridor_payout_method=route,
            provider=provider,
        )
        mock_request_json.return_value = {
            "base": "USD",
            "timestamp": 1776834000,
            "rates": {
                "GBP": "0.80000000",
                "ZMW": "25.60000000",
            },
        }

        response = self.client.get(
            reverse("rate-estimate"),
            {
                "source_country_id": str(uk.id),
                "destination_country_id": str(self.zambia.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["exchange_rate"]), "32.00000000")
        request_kwargs = mock_request_json.call_args.kwargs
        self.assertNotIn("symbols=", request_kwargs["path"])

    @override_settings(
        FX_RATE_SOURCE="open_exchange_rates",
        FX_RATE_SOURCE_CONFIGS={
            "open_exchange_rates": {
                "app_id": "test-app-id",
                "use_symbols": True,
            },
        },
    )
    @patch("apps.quotes.fx_sources.request_json")
    def test_rate_estimate_falls_back_to_frankfurter_when_primary_fails(
        self,
        mock_request_json,
    ):
        mock_request_json.side_effect = [
            ProviderRequestError("open exchange rates down"),
            {
                "base": "USD",
                "quote": "ZMW",
                "date": "2026-04-22",
                "rate": "25.70000000",
            },
        ]

        response = self.client.get(
            reverse("rate-estimate"),
            {
                "source_country_id": str(self.us.id),
                "destination_country_id": str(self.zambia.id),
                "send_amount": "100.00",
                "payout_method": PayoutMethod.MOBILE_MONEY,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["exchange_rate"]), "25.70000000")
        self.assertEqual(str(response.data["receive_amount"]), "2570.00")
        self.assertEqual(response.data["rate_source"], "frankfurter")
        self.assertEqual(response.data["rate_provider_name"], "frankfurter")
        self.assertFalse(response.data["is_primary_rate"])
        self.assertTrue(response.data["is_live_rate"])
        fallback_request_kwargs = mock_request_json.call_args_list[1].kwargs
        self.assertEqual(fallback_request_kwargs["method"], "GET")
        self.assertEqual(fallback_request_kwargs["path"], "/v2/rate/USD/ZMW")
        self.assertFalse(fallback_request_kwargs["include_api_key_auth"])

    @override_settings(
        FX_RATE_SOURCE="open_exchange_rates",
        FX_RATE_SOURCE_CONFIGS={
            "open_exchange_rates": {
                "app_id": "test-app-id",
                "use_symbols": True,
            },
        },
    )
    @patch("apps.quotes.fx_sources.request_json")
    def test_rate_estimate_falls_back_to_database_when_live_sources_fail(
        self,
        mock_request_json,
    ):
        mock_request_json.side_effect = [
            ProviderRequestError("open exchange rates down"),
            ProviderRequestError("frankfurter down"),
        ]

        response = self.client.get(
            reverse("rate-estimate"),
            {
                "source_country_id": str(self.us.id),
                "destination_country_id": str(self.zambia.id),
                "send_amount": "100.00",
                "payout_method": PayoutMethod.MOBILE_MONEY,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(str(response.data["exchange_rate"]), "25.50000000")
        self.assertEqual(str(response.data["receive_amount"]), "2550.00")
        self.assertEqual(response.data["rate_source"], "database")
        self.assertEqual(response.data["rate_provider_name"], "test_rate")
        self.assertFalse(response.data["is_primary_rate"])
        self.assertFalse(response.data["is_live_rate"])
        self.assertEqual(mock_request_json.call_count, 2)
