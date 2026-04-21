from django.urls import path

from .views import (
    StaffTransferAmlFlagReviewView,
    StaffTransferComplianceActionView,
    StaffTransferListView,
    StaffTransferSanctionsCheckReviewView,
    StaffTransferStatusTransitionView,
    TransferDetailView,
    TransferPaymentAuthorizationView,
    TransferFundingView,
    TransferListCreateView,
    TransferPaymentInstructionView,
    TransferPaymentWebhookView,
)


urlpatterns = [
    path("", TransferListCreateView.as_view(), name="transfer-list-create"),
    path(
        "payment-webhooks/<str:provider_name>/",
        TransferPaymentWebhookView.as_view(),
        name="transfer-payment-webhook",
    ),
    path(
        "operations/",
        StaffTransferListView.as_view(),
        name="transfer-operations-list",
    ),
    path("<uuid:pk>/funding/", TransferFundingView.as_view(), name="transfer-funding"),
    path(
        "<uuid:pk>/payment-instructions/",
        TransferPaymentInstructionView.as_view(),
        name="transfer-payment-instructions",
    ),
    path(
        "<uuid:pk>/payment-instructions/<uuid:instruction_id>/authorize/",
        TransferPaymentAuthorizationView.as_view(),
        name="transfer-payment-instruction-authorize",
    ),
    path(
        "<uuid:pk>/status/",
        StaffTransferStatusTransitionView.as_view(),
        name="transfer-status-transition",
    ),
    path(
        "<uuid:pk>/compliance-actions/",
        StaffTransferComplianceActionView.as_view(),
        name="transfer-compliance-action",
    ),
    path(
        "<uuid:pk>/sanctions-checks/<uuid:check_id>/review/",
        StaffTransferSanctionsCheckReviewView.as_view(),
        name="transfer-sanctions-check-review",
    ),
    path(
        "<uuid:pk>/aml-flags/<uuid:flag_id>/review/",
        StaffTransferAmlFlagReviewView.as_view(),
        name="transfer-aml-flag-review",
    ),
    path("<uuid:pk>/", TransferDetailView.as_view(), name="transfer-detail"),
]
