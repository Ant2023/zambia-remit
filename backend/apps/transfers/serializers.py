from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.countries.serializers import (
    CountrySerializer,
    CurrencySerializer,
    PayoutProviderSerializer,
)
from apps.countries.services import select_payout_provider
from apps.quotes.models import Quote
from apps.quotes.services import get_active_corridor
from apps.recipients.models import Recipient
from apps.recipients.serializers import RecipientSerializer
from common.choices import PayoutMethod

from .compliance import evaluate_transfer_compliance
from .models import (
    Transfer,
    TransferComplianceEvent,
    TransferComplianceFlag,
    TransferPaymentAction,
    TransferPaymentInstruction,
    TransferPaymentWebhookEvent,
    TransferPayoutAttempt,
    TransferPayoutEvent,
    TransferSanctionsCheck,
    TransferStatusEvent,
)
from .notifications import notify_transfer_created, notify_verification_required
from .services import get_allowed_status_transitions


class MockFundingSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(
        choices=TransferPaymentInstruction.PaymentMethod.choices,
    )
    payment_instruction_id = serializers.UUIDField(required=False, allow_null=True)
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


class TransferPaymentInstructionCreateSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(
        choices=TransferPaymentInstruction.PaymentMethod.choices,
    )


class CardPaymentAuthorizationSerializer(serializers.Serializer):
    cardholder_name = serializers.CharField(max_length=120)
    card_number = serializers.CharField(max_length=24)
    expiry_month = serializers.IntegerField(min_value=1, max_value=12)
    expiry_year = serializers.IntegerField(min_value=2024, max_value=2100)
    cvv = serializers.CharField(min_length=3, max_length=4)
    billing_postal_code = serializers.CharField(max_length=16)

    def validate_cardholder_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter the cardholder name.")
        return value

    def validate_card_number(self, value):
        digits_only = "".join(character for character in value if character.isdigit())
        if len(digits_only) < 13 or len(digits_only) > 19:
            raise serializers.ValidationError("Enter a valid card number.")
        return digits_only

    def validate_cvv(self, value):
        digits_only = "".join(character for character in value if character.isdigit())
        if len(digits_only) not in {3, 4}:
            raise serializers.ValidationError("Enter a valid security code.")
        return digits_only

    def validate_billing_postal_code(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Enter a valid billing ZIP or postal code.")
        return value


class PaymentWebhookEventCreateSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=120)
    event_type = serializers.CharField(max_length=120)
    provider_reference = serializers.CharField(max_length=64)
    payment_status = serializers.ChoiceField(
        choices=(
            TransferPaymentInstruction.Status.AUTHORIZED,
            TransferPaymentInstruction.Status.PAID,
            TransferPaymentInstruction.Status.FAILED,
            TransferPaymentInstruction.Status.CANCELLED,
            TransferPaymentInstruction.Status.REQUIRES_REVIEW,
            TransferPaymentInstruction.Status.EXPIRED,
            TransferPaymentInstruction.Status.REVERSED,
            TransferPaymentInstruction.Status.REFUNDED,
        ),
    )
    status_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    currency_code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=8,
    )
    event_created_at = serializers.DateTimeField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        attrs["event_id"] = attrs["event_id"].strip()
        attrs["event_type"] = attrs["event_type"].strip()
        attrs["provider_reference"] = attrs["provider_reference"].strip()
        attrs["status_reason"] = attrs.get("status_reason", "").strip()
        attrs["currency_code"] = attrs.get("currency_code", "").strip().upper()
        attrs["metadata"] = attrs.get("metadata") or {}

        if not attrs["event_id"]:
            raise serializers.ValidationError({"event_id": "Event id is required."})
        if not attrs["event_type"]:
            raise serializers.ValidationError(
                {"event_type": "Event type is required."},
            )
        if not attrs["provider_reference"]:
            raise serializers.ValidationError(
                {"provider_reference": "Provider reference is required."},
            )

        return attrs


class PaymentWebhookEventSerializer(serializers.ModelSerializer):
    payment_instruction_id = serializers.UUIDField(read_only=True)
    processing_status_display = serializers.CharField(
        source="get_processing_status_display",
        read_only=True,
    )

    class Meta:
        model = TransferPaymentWebhookEvent
        fields = (
            "id",
            "payment_instruction_id",
            "provider_name",
            "provider_event_id",
            "event_type",
            "provider_reference",
            "payload",
            "processing_status",
            "processing_status_display",
            "processing_message",
            "resulting_payment_status",
            "event_created_at",
            "processed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TransferPaymentActionCreateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=TransferPaymentAction.Action.choices)
    payment_instruction_id = serializers.UUIDField(required=False, allow_null=True)
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        min_value=Decimal("0.01"),
    )
    reason_code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=80,
    )
    note = serializers.CharField(max_length=1000)

    def validate_note(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Add a note for this payment action.")
        return value

    def validate_reason_code(self, value):
        return value.strip()


class TransferPaymentActionSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    currency = CurrencySerializer(read_only=True)
    requested_by_email = serializers.EmailField(
        source="requested_by.email",
        read_only=True,
    )

    class Meta:
        model = TransferPaymentAction
        fields = (
            "id",
            "transfer",
            "payment_instruction",
            "action",
            "action_display",
            "status",
            "status_display",
            "amount",
            "currency",
            "provider_name",
            "provider_reference",
            "provider_action_reference",
            "reason_code",
            "note",
            "failure_reason",
            "metadata",
            "requested_by_email",
            "processed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TransferPayoutAttemptSerializer(serializers.ModelSerializer):
    provider = PayoutProviderSerializer(read_only=True)
    currency = CurrencySerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = TransferPayoutAttempt
        fields = (
            "id",
            "transfer",
            "retry_of",
            "provider",
            "payout_method",
            "provider_reference",
            "attempt_number",
            "amount",
            "currency",
            "status",
            "status_display",
            "provider_status",
            "status_reason",
            "destination_snapshot",
            "request_payload",
            "response_payload",
            "submitted_at",
            "completed_at",
            "failed_at",
            "reversed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TransferPayoutEventSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    performed_by_email = serializers.EmailField(
        source="performed_by.email",
        read_only=True,
    )

    class Meta:
        model = TransferPayoutEvent
        fields = (
            "id",
            "transfer",
            "payout_attempt",
            "action",
            "action_display",
            "from_payout_status",
            "to_payout_status",
            "provider_event_id",
            "note",
            "metadata",
            "performed_by_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TransferPayoutAttemptSubmitSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_note(self, value):
        return value.strip()


class TransferPayoutStatusSyncSerializer(serializers.Serializer):
    payout_status = serializers.ChoiceField(
        choices=TransferPayoutAttempt.Status.choices,
    )
    provider_event_id = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
    )
    provider_status = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=80,
    )
    status_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        attrs["provider_event_id"] = attrs.get("provider_event_id", "").strip()
        attrs["provider_status"] = attrs.get("provider_status", "").strip()
        attrs["status_reason"] = attrs.get("status_reason", "").strip()
        attrs["metadata"] = attrs.get("metadata") or {}
        return attrs


class PayoutWebhookEventCreateSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=120)
    provider_reference = serializers.CharField(max_length=64)
    payout_status = serializers.ChoiceField(
        choices=TransferPayoutAttempt.Status.choices,
    )
    provider_status = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=80,
    )
    status_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )
    metadata = serializers.JSONField(required=False)
    event_created_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate(self, attrs):
        attrs["event_id"] = attrs["event_id"].strip()
        attrs["provider_reference"] = attrs["provider_reference"].strip()
        attrs["provider_status"] = attrs.get("provider_status", "").strip()
        attrs["status_reason"] = attrs.get("status_reason", "").strip()
        attrs["metadata"] = attrs.get("metadata") or {}

        if not attrs["event_id"]:
            raise serializers.ValidationError({"event_id": "Event id is required."})
        if not attrs["provider_reference"]:
            raise serializers.ValidationError(
                {"provider_reference": "Provider reference is required."},
            )

        return attrs


class TransferPayoutAttemptActionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000)

    def validate_note(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Add a note for this payout action.")
        return value


class TransferPaymentInstructionSerializer(serializers.ModelSerializer):
    instructions = serializers.SerializerMethodField()
    payment_method_display = serializers.CharField(
        source="get_payment_method_display",
        read_only=True,
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    currency = CurrencySerializer(read_only=True)

    class Meta:
        model = TransferPaymentInstruction
        fields = (
            "id",
            "transfer",
            "payment_method",
            "payment_method_display",
            "provider_name",
            "provider_reference",
            "amount",
            "currency",
            "status",
            "status_display",
            "status_reason",
            "instructions",
            "expires_at",
            "authorized_at",
            "completed_at",
            "failed_at",
            "reversed_at",
            "refunded_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_instructions(self, obj):
        sensitive_keys = {
            "authorization_cardholder_name",
            "authorization_cardholder_name_encrypted",
            "authorization_billing_postal_code",
        }
        return {
            key: value
            for key, value in obj.instructions.items()
            if key not in sensitive_keys and not key.endswith("_encrypted")
        }


class TransferComplianceFlagSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display",
        read_only=True,
    )
    severity_display = serializers.CharField(
        source="get_severity_display",
        read_only=True,
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    resolved_by_email = serializers.EmailField(source="resolved_by.email", read_only=True)

    class Meta:
        model = TransferComplianceFlag
        fields = (
            "id",
            "category",
            "category_display",
            "severity",
            "severity_display",
            "status",
            "status_display",
            "code",
            "title",
            "description",
            "metadata",
            "created_by_email",
            "resolved_by_email",
            "resolved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TransferComplianceEventSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    performed_by_email = serializers.EmailField(
        source="performed_by.email",
        read_only=True,
    )
    from_compliance_status_display = serializers.SerializerMethodField()
    to_compliance_status_display = serializers.SerializerMethodField()
    from_transfer_status_display = serializers.SerializerMethodField()
    to_transfer_status_display = serializers.SerializerMethodField()

    class Meta:
        model = TransferComplianceEvent
        fields = (
            "id",
            "action",
            "action_display",
            "from_compliance_status",
            "from_compliance_status_display",
            "to_compliance_status",
            "to_compliance_status_display",
            "from_transfer_status",
            "from_transfer_status_display",
            "to_transfer_status",
            "to_transfer_status_display",
            "note",
            "metadata",
            "performed_by_email",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_from_compliance_status_display(self, obj):
        if not obj.from_compliance_status:
            return ""
        return dict(Transfer.ComplianceStatus.choices).get(
            obj.from_compliance_status,
            obj.from_compliance_status,
        )

    def get_to_compliance_status_display(self, obj):
        if not obj.to_compliance_status:
            return ""
        return dict(Transfer.ComplianceStatus.choices).get(
            obj.to_compliance_status,
            obj.to_compliance_status,
        )

    def get_from_transfer_status_display(self, obj):
        if not obj.from_transfer_status:
            return ""
        return dict(Transfer.Status.choices).get(
            obj.from_transfer_status,
            obj.from_transfer_status,
        )

    def get_to_transfer_status_display(self, obj):
        if not obj.to_transfer_status:
            return ""
        return dict(Transfer.Status.choices).get(
            obj.to_transfer_status,
            obj.to_transfer_status,
        )


class TransferSanctionsCheckSerializer(serializers.ModelSerializer):
    party_type_display = serializers.CharField(
        source="get_party_type_display",
        read_only=True,
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True)

    class Meta:
        model = TransferSanctionsCheck
        fields = (
            "id",
            "party_type",
            "party_type_display",
            "status",
            "status_display",
            "screened_name",
            "provider_name",
            "provider_reference",
            "screening_payload",
            "response_payload",
            "match_score",
            "reviewed_by_email",
            "reviewed_at",
            "review_note",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class TransferStatusTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Transfer.Status.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class TransferSanctionsCheckReviewSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            TransferSanctionsCheck.Status.CLEAR,
            TransferSanctionsCheck.Status.POSSIBLE_MATCH,
            TransferSanctionsCheck.Status.CONFIRMED_MATCH,
            TransferSanctionsCheck.Status.ERROR,
            TransferSanctionsCheck.Status.SKIPPED,
        ),
    )
    review_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )
    provider_reference = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
    )
    match_score = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        status = attrs["status"]
        note = attrs.get("review_note", "").strip()

        if status in {
            TransferSanctionsCheck.Status.POSSIBLE_MATCH,
            TransferSanctionsCheck.Status.CONFIRMED_MATCH,
            TransferSanctionsCheck.Status.ERROR,
        } and not note:
            raise serializers.ValidationError(
                {"review_note": "Add a note for matched or failed screenings."},
            )

        attrs["review_note"] = note
        return attrs


class TransferComplianceActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=(
            TransferComplianceEvent.Action.NOTE,
            TransferComplianceEvent.Action.HOLD,
            TransferComplianceEvent.Action.REVIEW,
            TransferComplianceEvent.Action.APPROVE,
            TransferComplianceEvent.Action.REJECT,
        ),
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        action = attrs["action"]
        note = attrs.get("note", "").strip()

        if action in {
            TransferComplianceEvent.Action.NOTE,
            TransferComplianceEvent.Action.HOLD,
            TransferComplianceEvent.Action.REJECT,
        } and not note:
            raise serializers.ValidationError(
                {"note": "Add a note for this compliance action."},
            )

        attrs["note"] = note
        return attrs


class TransferAmlFlagReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=(
            "acknowledge",
            "review",
            "escalate",
            "clear",
            "dismiss",
            "report",
        ),
    )
    review_note = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000,
    )
    escalation_destination = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
    )
    escalation_reference = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=120,
    )

    def validate(self, attrs):
        decision = attrs["decision"]
        review_note = attrs.get("review_note", "").strip()
        escalation_destination = attrs.get("escalation_destination", "").strip()
        escalation_reference = attrs.get("escalation_reference", "").strip()

        if decision in {"review", "escalate", "dismiss", "report"} and not review_note:
            raise serializers.ValidationError(
                {"review_note": "Add a note for this AML action."},
            )

        if decision in {"escalate", "report"} and not escalation_destination:
            raise serializers.ValidationError(
                {
                    "escalation_destination": (
                        "Choose where this AML alert is being escalated."
                    ),
                },
            )

        attrs["review_note"] = review_note
        attrs["escalation_destination"] = escalation_destination
        attrs["escalation_reference"] = escalation_reference
        return attrs


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
    latest_payment_instruction = serializers.SerializerMethodField()
    latest_payout_attempt = serializers.SerializerMethodField()
    sender_email = serializers.EmailField(source="sender.email", read_only=True)
    sender_name = serializers.SerializerMethodField()
    recipient_details = RecipientSerializer(source="recipient", read_only=True)
    source_country_details = CountrySerializer(source="source_country", read_only=True)
    destination_country_details = CountrySerializer(
        source="destination_country",
        read_only=True,
    )
    source_currency_details = CurrencySerializer(source="source_currency", read_only=True)
    destination_currency_details = CurrencySerializer(
        source="destination_currency",
        read_only=True,
    )
    payout_provider_details = PayoutProviderSerializer(
        source="payout_provider",
        read_only=True,
    )

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
            "source_country_details",
            "destination_country",
            "destination_country_details",
            "source_currency",
            "source_currency_details",
            "destination_currency",
            "destination_currency_details",
            "payout_method",
            "payout_provider",
            "payout_provider_details",
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
            "sender_email",
            "sender_name",
            "recipient_details",
            "status_events",
            "latest_payment_instruction",
            "latest_payout_attempt",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "reference",
            "quote",
            "recipient",
            "source_country",
            "source_country_details",
            "destination_country",
            "destination_country_details",
            "source_currency",
            "source_currency_details",
            "destination_currency",
            "destination_currency_details",
            "payout_method",
            "payout_provider",
            "payout_provider_details",
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
            "sender_email",
            "sender_name",
            "recipient_details",
            "status_events",
            "latest_payment_instruction",
            "latest_payout_attempt",
            "created_at",
            "updated_at",
        )

    def get_latest_payment_instruction(self, obj):
        instruction = obj.payment_instructions.first()
        if not instruction:
            return None
        return TransferPaymentInstructionSerializer(instruction).data

    def get_latest_payout_attempt(self, obj):
        attempt = obj.payout_attempts.first()
        if not attempt:
            return None
        return TransferPayoutAttemptSerializer(attempt).data

    def get_sender_name(self, obj):
        name = f"{obj.sender.first_name} {obj.sender.last_name}".strip()
        return name or obj.sender.email

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
        corridor = get_active_corridor(
            quote.source_country_id,
            quote.destination_country_id,
        )
        provider_selection = select_payout_provider(
            corridor,
            quote.payout_method,
            quote.send_amount,
        )

        attrs["quote"] = quote
        attrs["recipient"] = recipient
        attrs["payout_provider"] = provider_selection.provider
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
        payout_provider = validated_data["payout_provider"]

        transfer = Transfer.objects.create(
            sender=request.user,
            recipient=recipient,
            quote=quote,
            source_country=quote.source_country,
            destination_country=quote.destination_country,
            source_currency=quote.source_currency,
            destination_currency=quote.destination_currency,
            payout_method=quote.payout_method,
            payout_provider=payout_provider,
            send_amount=quote.send_amount,
            fee_amount=quote.fee_amount,
            exchange_rate=quote.exchange_rate,
            receive_amount=quote.receive_amount,
            reason_for_transfer=validated_data.get("reason_for_transfer", ""),
        )
        compliance_flags = evaluate_transfer_compliance(transfer, changed_by=request.user)
        status_event = TransferStatusEvent.objects.create(
            transfer=transfer,
            from_status="",
            to_status=transfer.status,
            changed_by=request.user,
            note="Transfer created.",
        )
        notify_transfer_created(transfer, status_event=status_event)
        notify_verification_required(transfer, flags=compliance_flags)
        quote.status = Quote.Status.USED
        quote.save(update_fields=("status", "updated_at"))
        return transfer


class StaffTransferSerializer(TransferSerializer):
    allowed_next_statuses = serializers.SerializerMethodField()
    compliance_flags = TransferComplianceFlagSerializer(many=True, read_only=True)
    compliance_events = TransferComplianceEventSerializer(many=True, read_only=True)
    sanctions_checks = TransferSanctionsCheckSerializer(many=True, read_only=True)
    payment_actions = TransferPaymentActionSerializer(many=True, read_only=True)
    payout_attempts = TransferPayoutAttemptSerializer(many=True, read_only=True)
    payout_events = TransferPayoutEventSerializer(many=True, read_only=True)

    class Meta(TransferSerializer.Meta):
        fields = TransferSerializer.Meta.fields + (
            "allowed_next_statuses",
            "compliance_flags",
            "compliance_events",
            "sanctions_checks",
            "payment_actions",
            "payout_attempts",
            "payout_events",
        )
        read_only_fields = TransferSerializer.Meta.read_only_fields + (
            "allowed_next_statuses",
            "compliance_flags",
            "compliance_events",
            "sanctions_checks",
            "payment_actions",
            "payout_attempts",
            "payout_events",
        )

    def get_allowed_next_statuses(self, obj):
        return get_allowed_status_transitions(obj)
