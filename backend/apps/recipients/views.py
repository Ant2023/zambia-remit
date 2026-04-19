from rest_framework import generics, permissions

from .models import Recipient
from .serializers import RecipientSerializer


class RecipientListCreateView(generics.ListCreateAPIView):
    serializer_class = RecipientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Recipient.objects.select_related("country__currency")
            .prefetch_related("mobile_money_accounts", "bank_accounts")
            .filter(sender=self.request.user)
        )
