from django.urls import path

from .views import (
    ActiveCountryCorridorListView,
    CurrencyListView,
    EnabledDestinationCountryListView,
    EnabledSenderCountryListView,
)


urlpatterns = [
    path("currencies/", CurrencyListView.as_view(), name="currency-list"),
    path(
        "sender-countries/",
        EnabledSenderCountryListView.as_view(),
        name="enabled-sender-country-list",
    ),
    path(
        "destination-countries/",
        EnabledDestinationCountryListView.as_view(),
        name="enabled-destination-country-list",
    ),
    path("corridors/", ActiveCountryCorridorListView.as_view(), name="corridor-list"),
]
