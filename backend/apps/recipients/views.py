from django.db.models import ProtectedError
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Recipient
from .serializers import RecipientSerializer, RecipientVerificationReviewSerializer


def get_recipient_queryset(user):
    return (
        Recipient.objects.select_related("country__currency")
        .prefetch_related("mobile_money_accounts", "bank_accounts")
        .filter(sender=user)
    )


class RecipientListCreateView(generics.ListCreateAPIView):
    serializer_class = RecipientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_recipient_queryset(self.request.user)


class RecipientDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RecipientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_recipient_queryset(self.request.user)

    def perform_destroy(self, instance):
        if instance.transfers.exists():
            raise ValidationError(
                {
                    "detail": (
                        "Recipients with submitted transfers cannot be deleted."
                    )
                },
            )

        try:
            instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                {
                    "detail": (
                        "This recipient is linked to protected transaction records."
                    )
                },
            ) from exc


class RecipientVerificationSubmitView(generics.GenericAPIView):
    serializer_class = RecipientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_recipient_queryset(self.request.user)

    def post(self, request, *args, **kwargs):
        recipient = self.get_object()

        if not recipient.is_verification_ready:
            return Response(
                {
                    "detail": (
                        "Complete the recipient payout details before submitting verification."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if recipient.verification_status == Recipient.VerificationStatus.PENDING:
            return Response(
                {"detail": "This recipient is already pending review."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if recipient.verification_status == Recipient.VerificationStatus.VERIFIED:
            return Response(
                {"detail": "This recipient is already verified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        recipient.submit_verification()
        return Response(RecipientSerializer(recipient).data)


class StaffRecipientVerificationReviewView(generics.GenericAPIView):
    serializer_class = RecipientVerificationReviewSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Recipient.objects.select_related(
        "sender",
        "country__currency",
        "verification_reviewed_by",
    ).prefetch_related("mobile_money_accounts", "bank_accounts")

    def post(self, request, *args, **kwargs):
        recipient = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        next_status = serializer.validated_data["verification_status"]
        if (
            next_status == Recipient.VerificationStatus.VERIFIED
            and not recipient.is_verification_ready
        ):
            return Response(
                {
                    "detail": (
                        "Recipient payout details must be complete before verification."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        recipient.mark_verification_reviewed(
            status=next_status,
            reviewed_by=request.user,
            note=serializer.validated_data["review_note"],
        )
        return Response(RecipientSerializer(recipient).data)
