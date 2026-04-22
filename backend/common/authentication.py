from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        ttl_hours = getattr(settings, "AUTH_TOKEN_TTL_HOURS", 0)

        if ttl_hours and token.created <= timezone.now() - timedelta(hours=ttl_hours):
            token.delete()
            raise AuthenticationFailed("Authentication token expired.")

        return user, token
