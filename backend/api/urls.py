from django.urls import include, path

from .views import health_check


urlpatterns = [
    path("health/", health_check, name="api-health"),
    path("accounts/", include("apps.accounts.urls")),
    path("countries/", include("apps.countries.urls")),
    path("recipients/", include("apps.recipients.urls")),
    path("quotes/", include("apps.quotes.urls")),
    path("transfers/", include("apps.transfers.urls")),
]
