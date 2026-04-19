from django.urls import path

from .views import TransferDetailView, TransferFundingView, TransferListCreateView


urlpatterns = [
    path("", TransferListCreateView.as_view(), name="transfer-list-create"),
    path("<uuid:pk>/funding/", TransferFundingView.as_view(), name="transfer-funding"),
    path("<uuid:pk>/", TransferDetailView.as_view(), name="transfer-detail"),
]
