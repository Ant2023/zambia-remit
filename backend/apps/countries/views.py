from django.db.models import Prefetch
from rest_framework import generics, permissions

from .models import (
    CorridorPayoutMethod,
    CorridorPayoutProvider,
    Country,
    CountryCorridor,
    Currency,
)
from .serializers import (
    CountryCorridorSerializer,
    CountrySerializer,
    CurrencySerializer,
)


class CurrencyListView(generics.ListAPIView):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    permission_classes = [permissions.AllowAny]


class EnabledSenderCountryListView(generics.ListAPIView):
    serializer_class = CountrySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Country.objects.select_related("currency").filter(
            is_sender_enabled=True,
        )


class EnabledDestinationCountryListView(generics.ListAPIView):
    serializer_class = CountrySerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Country.objects.select_related("currency").filter(
            is_destination_enabled=True,
        )


class ActiveCountryCorridorListView(generics.ListAPIView):
    serializer_class = CountryCorridorSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        active_provider_routes = CorridorPayoutProvider.objects.select_related(
            "provider",
        ).filter(
            is_active=True,
            provider__is_active=True,
        ).order_by("priority", "provider__name")

        active_payout_methods = (
            CorridorPayoutMethod.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "providers",
                    queryset=active_provider_routes,
                    to_attr="active_providers",
                ),
            )
            .order_by("display_order", "payout_method")
        )

        return CountryCorridor.objects.select_related(
            "source_country__currency",
            "destination_country__currency",
            "source_currency",
            "destination_currency",
        ).prefetch_related(
            Prefetch(
                "payout_methods",
                queryset=active_payout_methods,
                to_attr="active_payout_methods",
            ),
        ).filter(is_active=True)
