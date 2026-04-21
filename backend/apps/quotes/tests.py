from decimal import Decimal

from django.contrib.auth import get_user_model
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

from .models import ExchangeRate, FeeRule, Quote


User = get_user_model()


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
