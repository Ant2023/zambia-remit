from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Transfer, TransferStatusEvent
from .serializers import MockFundingSerializer, TransferSerializer


def get_transfer_queryset(user):
    return (
        Transfer.objects.select_related(
            "recipient",
            "quote",
            "source_country",
            "destination_country",
            "source_currency",
            "destination_currency",
        )
        .prefetch_related("status_events")
        .filter(sender=user)
    )


class TransferListCreateView(generics.ListCreateAPIView):
    serializer_class = TransferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_transfer_queryset(self.request.user)


class TransferDetailView(generics.RetrieveAPIView):
    serializer_class = TransferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_transfer_queryset(self.request.user)


class TransferFundingView(generics.GenericAPIView):
    serializer_class = MockFundingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_transfer_queryset(self.request.user)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if (
            transfer.status == Transfer.Status.FUNDING_RECEIVED
            and transfer.funding_status == Transfer.FundingStatus.RECEIVED
        ):
            return Response(TransferSerializer(transfer).data)

        if transfer.status != Transfer.Status.AWAITING_FUNDING:
            return Response(
                {
                    "detail": (
                        "Only transfers awaiting funding can be marked as funded."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous_status = transfer.status
        payment_method = serializer.validated_data["payment_method"]
        payment_method_label = MockFundingSerializer.PaymentMethod.labels[
            payment_method
        ]
        note = serializer.validated_data.get("note", "").strip()
        event_note = f"Mock funding received via {payment_method_label}."

        if note:
            event_note = f"{event_note} {note}"

        transfer.status = Transfer.Status.FUNDING_RECEIVED
        transfer.funding_status = Transfer.FundingStatus.RECEIVED
        transfer.save(update_fields=("status", "funding_status", "updated_at"))

        TransferStatusEvent.objects.create(
            transfer=transfer,
            from_status=previous_status,
            to_status=transfer.status,
            changed_by=request.user,
            note=event_note,
        )

        refreshed_transfer = get_transfer_queryset(request.user).get(pk=transfer.pk)
        return Response(TransferSerializer(refreshed_transfer).data)
