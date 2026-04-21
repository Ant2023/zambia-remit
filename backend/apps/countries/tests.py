from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from common.choices import PayoutMethod

from .models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    Country,
    CountryCorridor,
    Currency,
    PayoutProvider,
)
from .services import select_payout_provider


class CorridorPayoutRouteTests(APITestCase):
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
        self.provider = PayoutProvider.objects.create(
            code="test_country_mobile_money",
            name="Test country mobile money",
            payout_method=PayoutMethod.MOBILE_MONEY,
        )
        self.payout_method = CorridorPayoutMethod.objects.create(
            corridor=self.corridor,
            payout_method=PayoutMethod.MOBILE_MONEY,
            display_order=10,
        )
        CorridorPayoutProvider.objects.create(
            corridor_payout_method=self.payout_method,
            provider=self.provider,
            priority=10,
        )

    def test_active_corridors_include_payout_methods_and_providers(self):
        response = self.client.get(reverse("corridor-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        payout_methods = response.data[0]["payout_methods"]
        self.assertEqual(payout_methods[0]["payout_method"], PayoutMethod.MOBILE_MONEY)
        provider = payout_methods[0]["providers"][0]["provider"]
        self.assertEqual(provider["code"], "test_country_mobile_money")

    def test_select_payout_provider_uses_highest_priority_active_route(self):
        priority_provider = PayoutProvider.objects.create(
            code="priority_mobile_money",
            name="Priority mobile money",
            payout_method=PayoutMethod.MOBILE_MONEY,
        )
        CorridorPayoutProvider.objects.create(
            corridor_payout_method=self.payout_method,
            provider=priority_provider,
            priority=1,
        )

        selection = select_payout_provider(
            self.corridor,
            PayoutMethod.MOBILE_MONEY,
            Decimal("100.00"),
        )

        self.assertEqual(selection.provider, priority_provider)
