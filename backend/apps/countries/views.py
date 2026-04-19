from rest_framework import generics, permissions

from .models import Country, CountryCorridor, Currency
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
        return CountryCorridor.objects.select_related(
            "source_country__currency",
            "destination_country__currency",
            "source_currency",
            "destination_currency",
        ).filter(is_active=True)
