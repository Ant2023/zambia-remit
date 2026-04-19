from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.quotes.models import Quote
from apps.recipients.models import Recipient
from common.choices import PayoutMethod

from .models import Transfer, TransferStatusEvent


class MockFundingSerializer(serializers.Serializer):
    class PaymentMethod:
        DEBIT_CARD = "debit_card"
        BANK_TRANSFER = "bank_transfer"

        choices = (
            (DEBIT_CARD, "Debit card"),
            (BANK_TRANSFER, "Bank transfer"),
        )

        labels = dict(choices)

    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=240,
    )


class TransferStatusEventSerializer(serializers.ModelSerializer):
    from_status_display = serializers.SerializerMethodField()
    to_status_display = serializers.SerializerMethodField()

    class Meta:
        model = TransferStatusEvent
        fields = (
            "id",
            "from_status",
            "from_status_display",
            "to_status",
            "to_status_display",
            "note",
            "created_at",
        )
        read_only_fields = fields

    def get_from_status_display(self, obj):
        if not obj.from_status:
            return ""
        return dict(Transfer.Status.choices).get(obj.from_status, obj.from_status)

    def get_to_status_display(self, obj):
        return dict(Transfer.Status.choices).get(obj.to_status, obj.to_status)


class TransferSerializer(serializers.ModelSerializer):
    quote_id = serializers.UUIDField(write_only=True)
    recipient_id = serializers.UUIDField(write_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    funding_status_display = serializers.CharField(
        source="get_funding_status_display",
        read_only=True,
    )
    compliance_status_display = serializers.CharField(
        source="get_compliance_status_display",
        read_only=True,
    )
    payout_status_display = serializers.CharField(
        source="get_payout_status_display",
        read_only=True,
    )
    status_events = TransferStatusEventSerializer(many=True, read_only=True)

    class Meta:
        model = Transfer
        fields = (
            "id",
            "reference",
            "quote",
            "quote_id",
            "recipient",
            "recipient_id",
            "source_country",
            "destination_country",
            "source_currency",
            "destination_currency",
            "payout_method",
            "send_amount",
            "fee_amount",
            "exchange_rate",
            "receive_amount",
            "status",
            "status_display",
            "funding_status",
            "funding_status_display",
            "compliance_status",
            "compliance_status_display",
            "payout_status",
            "payout_status_display",
            "reason_for_transfer",
            "status_events",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "reference",
            "quote",
            "recipient",
            "source_country",
            "destination_country",
            "source_currency",
            "destination_currency",
            "payout_method",
            "send_amount",
            "fee_amount",
            "exchange_rate",
            "receive_amount",
            "status",
            "status_display",
            "funding_status",
            "funding_status_display",
            "compliance_status",
            "compliance_status_display",
            "payout_status",
            "payout_status_display",
            "status_events",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        request = self.context["request"]
        quote_id = attrs.pop("quote_id")
        recipient_id = attrs.pop("recipient_id")

        try:
            quote = Quote.objects.select_related(
                "recipient",
                "source_country",
                "destination_country",
                "source_currency",
                "destination_currency",
            ).get(id=quote_id, sender=request.user)
        except Quote.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"quote_id": "Active quote not found."},
            ) from exc

        if quote.status != Quote.Status.ACTIVE:
            raise serializers.ValidationError(
                {"quote_id": "Only active quotes can create transfers."},
            )

        if quote.expires_at <= timezone.now():
            raise serializers.ValidationError({"quote_id": "Quote has expired."})

        if hasattr(quote, "transfer"):
            raise serializers.ValidationError(
                {"quote_id": "This quote has already been used."},
            )

        try:
            recipient = Recipient.objects.get(id=recipient_id, sender=request.user)
        except Recipient.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"recipient_id": "Recipient not found."},
            ) from exc

        if quote.recipient_id and quote.recipient_id != recipient.id:
            raise serializers.ValidationError(
                {"recipient_id": "Recipient must match the quote recipient."},
            )

        if recipient.country_id != quote.destination_country_id:
            raise serializers.ValidationError(
                {"recipient_id": "Recipient country must match quote destination."},
            )

        self.validate_recipient_payout_account(recipient, quote.payout_method)

        attrs["quote"] = quote
        attrs["recipient"] = recipient
        return attrs

    def validate_recipient_payout_account(self, recipient: Recipient, payout_method: str):
        if payout_method == PayoutMethod.MOBILE_MONEY:
            if not recipient.mobile_money_accounts.exists():
                raise serializers.ValidationError(
                    {"recipient_id": "Recipient needs a mobile money account."},
                )

        if payout_method == PayoutMethod.BANK_DEPOSIT:
            if not recipient.bank_accounts.exists():
                raise serializers.ValidationError(
                    {"recipient_id": "Recipient needs a bank account."},
                )

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        quote = validated_data["quote"]
        recipient = validated_data["recipient"]

        transfer = Transfer.objects.create(
            sender=request.user,
            recipient=recipient,
            quote=quote,
            source_country=quote.source_country,
            destination_country=quote.destination_country,
            source_currency=quote.source_currency,
            destination_currency=quote.destination_currency,
            payout_method=quote.payout_method,
            send_amount=quote.send_amount,
            fee_amount=quote.fee_amount,
            exchange_rate=quote.exchange_rate,
            receive_amount=quote.receive_amount,
            reason_for_transfer=validated_data.get("reason_for_transfer", ""),
        )
        TransferStatusEvent.objects.create(
            transfer=transfer,
            from_status="",
            to_status=transfer.status,
            changed_by=request.user,
            note="Transfer created.",
        )
        quote.status = Quote.Status.USED
        quote.save(update_fields=("status", "updated_at"))
        return transfer
