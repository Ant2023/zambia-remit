from django.urls import path

from .views import FeeRuleListView, QuoteListCreateView, RateEstimateView


urlpatterns = [
    path("", QuoteListCreateView.as_view(), name="quote-list-create"),
    path("rate/", RateEstimateView.as_view(), name="rate-estimate"),
    path("fee-rules/", FeeRuleListView.as_view(), name="fee-rule-list"),
]
