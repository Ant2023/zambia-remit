from django.urls import path

from .views import (
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegistrationView,
    SenderDocumentDetailView,
    SenderDocumentListCreateView,
    SenderKycSubmitView,
    SenderProfileView,
    StaffLoginView,
    StaffSenderDocumentDownloadView,
    StaffSenderDocumentListView,
    StaffSenderDocumentReviewView,
    StaffSenderKycReviewView,
)


urlpatterns = [
    path("register/", RegistrationView.as_view(), name="account-register"),
    path("login/", LoginView.as_view(), name="account-login"),
    path("staff-login/", StaffLoginView.as_view(), name="account-staff-login"),
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="account-password-reset",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="account-password-reset-confirm",
    ),
    path("logout/", LogoutView.as_view(), name="account-logout"),
    path("me/", MeView.as_view(), name="account-me"),
    path("profile/", SenderProfileView.as_view(), name="sender-profile"),
    path(
        "profile/documents/",
        SenderDocumentListCreateView.as_view(),
        name="sender-document-list",
    ),
    path(
        "profile/documents/<uuid:pk>/",
        SenderDocumentDetailView.as_view(),
        name="sender-document-detail",
    ),
    path(
        "profile/kyc-submit/",
        SenderKycSubmitView.as_view(),
        name="sender-kyc-submit",
    ),
    path(
        "profiles/<uuid:profile_id>/kyc-review/",
        StaffSenderKycReviewView.as_view(),
        name="sender-kyc-review",
    ),
    path(
        "staff/documents/",
        StaffSenderDocumentListView.as_view(),
        name="staff-sender-document-list",
    ),
    path(
        "staff/documents/<uuid:pk>/review/",
        StaffSenderDocumentReviewView.as_view(),
        name="staff-sender-document-review",
    ),
    path(
        "staff/documents/<uuid:pk>/download/",
        StaffSenderDocumentDownloadView.as_view(),
        name="staff-sender-document-download",
    ),
]
