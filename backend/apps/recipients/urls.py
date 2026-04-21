from django.urls import path

from .views import (
    RecipientDetailView,
    RecipientListCreateView,
    RecipientVerificationSubmitView,
    StaffRecipientVerificationReviewView,
)


urlpatterns = [
    path("", RecipientListCreateView.as_view(), name="recipient-list-create"),
    path(
        "<uuid:pk>/verification-submit/",
        RecipientVerificationSubmitView.as_view(),
        name="recipient-verification-submit",
    ),
    path(
        "<uuid:pk>/verification-review/",
        StaffRecipientVerificationReviewView.as_view(),
        name="recipient-verification-review",
    ),
    path("<uuid:pk>/", RecipientDetailView.as_view(), name="recipient-detail"),
]
