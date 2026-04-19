from django.urls import path

from .views import LoginView, LogoutView, MeView, RegistrationView, SenderProfileView


urlpatterns = [
    path("register/", RegistrationView.as_view(), name="account-register"),
    path("login/", LoginView.as_view(), name="account-login"),
    path("logout/", LogoutView.as_view(), name="account-logout"),
    path("me/", MeView.as_view(), name="account-me"),
    path("profile/", SenderProfileView.as_view(), name="sender-profile"),
]
