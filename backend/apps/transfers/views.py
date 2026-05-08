import csv
import secrets

from django.conf import settings
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from common.audit import record_operational_audit
from common.models import OperationalAuditLog

from .compliance import (
    apply_compliance_action,
    review_transfer_aml_flag,
    review_transfer_sanctions_check,
)
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
from .payment_processors import (
    StripePaymentProcessor,
    authorize_payment_instruction,
    get_payment_processor_by_provider,
    prepare_payment_instruction,
)
from .payment_fraud import evaluate_payment_fraud_rules
from .notifications import notify_payment_received
from .serializers import (
    CardPaymentAuthorizationSerializer,
    StripePaymentConfirmSerializer,
    TransferComplianceActionSerializer,
    MockFundingSerializer,
    PaymentWebhookEventCreateSerializer,
    PaymentWebhookEventSerializer,
    PayoutWebhookEventCreateSerializer,
    StaffExportQuerySerializer,
    StaffTransferSerializer,
    StaffReportQuerySerializer,
    TransferAmlFlagReviewSerializer,
    TransferPaymentActionCreateSerializer,
    TransferPaymentInstructionCreateSerializer,
    TransferPaymentInstructionSerializer,
    TransferPayoutAttemptActionSerializer,
    TransferPayoutAttemptSerializer,
    TransferPayoutAttemptSubmitSerializer,
    TransferPayoutStatusSyncSerializer,
    TransferSanctionsCheckReviewSerializer,
    TransferStatusTransitionSerializer,
    TransferSerializer,
)
from .reports import build_operations_report, make_report_window
from .payouts import (
    retry_payout_attempt,
    reverse_payout_attempt,
    sync_payout_attempt_status_from_provider,
    submit_payout_for_transfer,
    sync_payout_attempt_status,
)
from .services import (
    apply_payment_instruction_status,
    create_payment_action,
    process_payment_webhook_event,
    transition_transfer_status,
)


CSV_CONTENT_TYPE = "text/csv"
CSV_ROW_LIMIT = 10000


def get_transfer_queryset(user):
    compliance_flag_queryset = TransferComplianceFlag.objects.select_related(
        "created_by",
        "resolved_by",
    )
    compliance_event_queryset = TransferComplianceEvent.objects.select_related(
        "performed_by",
    )
    sanctions_check_queryset = TransferSanctionsCheck.objects.select_related(
        "reviewed_by",
    )
    payment_action_queryset = TransferPaymentAction.objects.select_related(
        "currency",
        "requested_by",
        "payment_instruction",
    )
    payout_attempt_queryset = TransferPayoutAttempt.objects.select_related(
        "provider",
        "currency",
        "created_by",
    )
    payout_event_queryset = TransferPayoutEvent.objects.select_related(
        "payout_attempt",
        "performed_by",
    )
    return (
        Transfer.objects.select_related(
            "sender",
            "recipient",
            "recipient__country__currency",
            "quote",
            "source_country",
            "source_country__currency",
            "destination_country",
            "destination_country__currency",
            "source_currency",
            "destination_currency",
            "payout_provider",
        )
        .prefetch_related(
            "recipient__mobile_money_accounts",
            "recipient__bank_accounts",
            "status_events",
            "payment_instructions",
            Prefetch("payout_attempts", queryset=payout_attempt_queryset),
            Prefetch("payout_events", queryset=payout_event_queryset),
            Prefetch("compliance_flags", queryset=compliance_flag_queryset),
            Prefetch("compliance_events", queryset=compliance_event_queryset),
            Prefetch("sanctions_checks", queryset=sanctions_check_queryset),
            Prefetch("payment_actions", queryset=payment_action_queryset),
        )
        .filter(sender=user)
    )


def get_payment_webhook_secret(provider_name: str) -> str:
    secrets_map = getattr(settings, "PAYMENT_WEBHOOK_SECRETS", {})
    if isinstance(secrets_map, dict):
        return str(secrets_map.get(provider_name, "")).strip()
    return ""


def get_payout_webhook_secret(provider_code: str) -> str:
    secrets_map = getattr(settings, "PAYOUT_WEBHOOK_SECRETS", {})
    if isinstance(secrets_map, dict):
        return str(secrets_map.get(provider_code, "")).strip()
    return ""


def validate_webhook_secret(request, *, expected_secret: str, header_name: str):
    if not expected_secret:
        if settings.DEBUG:
            return None
        return Response(
            {"detail": "Webhook secret is not configured."},
            status=status.HTTP_403_FORBIDDEN,
        )

    provided_secret = request.headers.get(header_name, "")
    if not secrets.compare_digest(provided_secret, expected_secret):
        return Response(
            {"detail": "Invalid webhook secret."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return None


def csv_value(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def recipient_full_name(recipient):
    return " ".join(
        part
        for part in (
            getattr(recipient, "first_name", ""),
            getattr(recipient, "last_name", ""),
        )
        if part
    ).strip()


def build_csv_response(filename: str, headers: list[str], rows):
    response = HttpResponse(content_type=CSV_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([csv_value(value) for value in row])
    return response


def apply_staff_export_date_window(queryset, serializer):
    start_at, end_at = make_report_window(
        serializer.validated_data.get("start_date"),
        serializer.validated_data.get("end_date"),
    )
    return queryset.filter(created_at__gte=start_at, created_at__lt=end_at)


def get_transfer_base_queryset():
    compliance_flag_queryset = TransferComplianceFlag.objects.select_related(
        "created_by",
        "resolved_by",
    )
    compliance_event_queryset = TransferComplianceEvent.objects.select_related(
        "performed_by",
    )
    sanctions_check_queryset = TransferSanctionsCheck.objects.select_related(
        "reviewed_by",
    )
    payment_action_queryset = TransferPaymentAction.objects.select_related(
        "currency",
        "requested_by",
        "payment_instruction",
    )
    payout_attempt_queryset = TransferPayoutAttempt.objects.select_related(
        "provider",
        "currency",
        "created_by",
    )
    payout_event_queryset = TransferPayoutEvent.objects.select_related(
        "payout_attempt",
        "performed_by",
    )
    return Transfer.objects.select_related(
        "sender",
        "recipient",
        "recipient__country__currency",
        "quote",
        "source_country",
        "source_country__currency",
        "destination_country",
        "destination_country__currency",
        "source_currency",
        "destination_currency",
        "payout_provider",
    ).prefetch_related(
        "recipient__mobile_money_accounts",
        "recipient__bank_accounts",
        "status_events",
        "payment_instructions",
        Prefetch("payout_attempts", queryset=payout_attempt_queryset),
        Prefetch("payout_events", queryset=payout_event_queryset),
        Prefetch("compliance_flags", queryset=compliance_flag_queryset),
        Prefetch("compliance_events", queryset=compliance_event_queryset),
        Prefetch("sanctions_checks", queryset=sanctions_check_queryset),
        Prefetch("payment_actions", queryset=payment_action_queryset),
    )


def record_transfer_operation_audit(
    request,
    *,
    action_name: str,
    transfer: Transfer,
    target_type: str = "transfer",
    target_id: str = "",
    previous_status: str = "",
    new_status: str = "",
    note: str = "",
    metadata: dict | None = None,
):
    return record_operational_audit(
        request=request,
        action_name=action_name,
        target_type=target_type,
        target_id=target_id or str(transfer.id),
        target_reference=transfer.reference,
        previous_status=previous_status,
        new_status=new_status,
        note=note,
        metadata=metadata or {},
    )


def create_payment_instruction(transfer, payment_method):
    instruction = TransferPaymentInstruction.objects.create(
        transfer=transfer,
        payment_method=payment_method,
        amount=transfer.send_amount + transfer.fee_amount,
        currency=transfer.source_currency,
        expires_at=None,
    )
    prepared_instruction = prepare_payment_instruction(
        transfer,
        payment_method,
        instruction.provider_reference,
    )
    instruction.provider_name = prepared_instruction.provider_name
    instruction.status = prepared_instruction.status
    instruction.instructions = prepared_instruction.instructions
    instruction.save(update_fields=("provider_name", "status", "instructions", "updated_at"))
    return instruction


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
        payment_method_label = TransferPaymentInstruction.PaymentMethod(
            payment_method,
        ).label
        note = serializer.validated_data.get("note", "").strip()
        payment_instruction = self.get_payment_instruction(
            transfer,
            payment_method,
            serializer.validated_data.get("payment_instruction_id"),
        )
        event_note = (
            "Development funding confirmation received via "
            f"{payment_method_label}."
        )

        if note:
            event_note = f"{event_note} {note}"

        if (
            payment_instruction
            and payment_method
            in {
                TransferPaymentInstruction.PaymentMethod.CREDIT_CARD,
                TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
            }
            and payment_instruction.status
            not in {
                TransferPaymentInstruction.Status.AUTHORIZED,
                TransferPaymentInstruction.Status.PAID,
            }
        ):
            raise ValidationError(
                {
                    "payment_instruction_id": (
                        "Card payment must be authorized before funding is confirmed."
                    ),
                },
            )

        if payment_instruction:
            fraud_flags = evaluate_payment_fraud_rules(
                payment_instruction,
                changed_by=request.user,
            )
            payment_instruction.refresh_from_db()
            if any(flag.metadata.get("action") == "hold" for flag in fraud_flags):
                return Response(
                    {
                        "payment_instruction_id": (
                            "Payment requires fraud review before funding can continue."
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if payment_instruction and not payment_instruction.is_completed:
            transfer = apply_payment_instruction_status(
                payment_instruction,
                TransferPaymentInstruction.Status.PAID,
                changed_by=request.user,
                note=event_note,
                status_reason=note,
            )
        else:
            transfer.status = Transfer.Status.FUNDING_RECEIVED
            transfer.funding_status = Transfer.FundingStatus.RECEIVED
            transfer.save(update_fields=("status", "funding_status", "updated_at"))

            status_event = TransferStatusEvent.objects.create(
                transfer=transfer,
                from_status=previous_status,
                to_status=transfer.status,
                changed_by=request.user,
                note=event_note,
            )
            notify_payment_received(
                transfer,
                status_event=status_event,
                note=event_note,
            )

        refreshed_transfer = get_transfer_queryset(request.user).get(pk=transfer.pk)
        return Response(TransferSerializer(refreshed_transfer).data)

    def get_payment_instruction(self, transfer, payment_method, instruction_id):
        if instruction_id:
            try:
                return TransferPaymentInstruction.objects.get(
                    id=instruction_id,
                    transfer=transfer,
                    payment_method=payment_method,
                )
            except TransferPaymentInstruction.DoesNotExist as exc:
                raise ValidationError(
                    {"payment_instruction_id": "Payment instruction not found."},
                ) from exc

        return (
            transfer.payment_instructions.filter(
                payment_method=payment_method,
                status__in=(
                    TransferPaymentInstruction.Status.NOT_STARTED,
                    TransferPaymentInstruction.Status.PENDING_AUTHORIZATION,
                    TransferPaymentInstruction.Status.AUTHORIZED,
                    TransferPaymentInstruction.Status.REQUIRES_REVIEW,
                ),
            )
            .order_by("-created_at")
            .first()
        )


class TransferPaymentInstructionView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_transfer_queryset(self.request.user)

    def get(self, request, *args, **kwargs):
        transfer = self.get_object()
        instructions = transfer.payment_instructions.all()
        serializer = TransferPaymentInstructionSerializer(instructions, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()

        if transfer.funding_status == Transfer.FundingStatus.RECEIVED:
            return Response(
                {"detail": "This transfer has already been funded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if transfer.status != Transfer.Status.AWAITING_FUNDING:
            return Response(
                {"detail": "Payment instructions are only available before funding."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TransferPaymentInstructionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        instruction = create_payment_instruction(
            transfer,
            serializer.validated_data["payment_method"],
        )
        response_serializer = TransferPaymentInstructionSerializer(instruction)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class TransferPaymentAuthorizationView(generics.GenericAPIView):
    serializer_class = CardPaymentAuthorizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_transfer_queryset(self.request.user)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            instruction = transfer.payment_instructions.get(id=self.kwargs["instruction_id"])
        except TransferPaymentInstruction.DoesNotExist as exc:
            raise ValidationError(
                {"instruction_id": "Payment instruction not found for this transfer."},
            ) from exc

        if instruction.payment_method not in {
            TransferPaymentInstruction.PaymentMethod.CREDIT_CARD,
            TransferPaymentInstruction.PaymentMethod.DEBIT_CARD,
        }:
            raise ValidationError(
                {"instruction_id": "Only card instructions support authorization."},
            )

        if instruction.status in {
            TransferPaymentInstruction.Status.PAID,
            TransferPaymentInstruction.Status.CANCELLED,
            TransferPaymentInstruction.Status.EXPIRED,
            TransferPaymentInstruction.Status.REVERSED,
            TransferPaymentInstruction.Status.REFUNDED,
        }:
            raise ValidationError(
                {"instruction_id": "This payment instruction can no longer be authorized."},
            )

        authorization_result = authorize_payment_instruction(
            instruction,
            cardholder_name=serializer.validated_data["cardholder_name"],
            card_number=serializer.validated_data["card_number"],
            expiry_month=serializer.validated_data["expiry_month"],
            expiry_year=serializer.validated_data["expiry_year"],
            cvv=serializer.validated_data["cvv"],
            billing_postal_code=serializer.validated_data["billing_postal_code"],
        )
        apply_payment_instruction_status(
            instruction,
            authorization_result.status,
            changed_by=request.user,
            note=authorization_result.status_reason,
            status_reason=authorization_result.status_reason,
            instruction_updates=authorization_result.instruction_updates,
        )
        instruction.refresh_from_db()
        evaluate_payment_fraud_rules(instruction, changed_by=request.user)
        instruction.refresh_from_db()
        return Response(TransferPaymentInstructionSerializer(instruction).data)


class TransferStripeConfirmView(generics.GenericAPIView):
    serializer_class = StripePaymentConfirmSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return get_transfer_queryset(self.request.user)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            instruction = transfer.payment_instructions.get(id=self.kwargs["instruction_id"])
        except TransferPaymentInstruction.DoesNotExist as exc:
            raise ValidationError(
                {"instruction_id": "Payment instruction not found for this transfer."},
            ) from exc

        if instruction.provider_name != StripePaymentProcessor.code:
            raise ValidationError(
                {"instruction_id": "This endpoint is only for Stripe payment instructions."},
            )

        if instruction.status in {
            TransferPaymentInstruction.Status.AUTHORIZED,
            TransferPaymentInstruction.Status.PAID,
        }:
            instruction.refresh_from_db()
            return Response(TransferPaymentInstructionSerializer(instruction).data)

        processor = StripePaymentProcessor()
        authorization_result = processor.verify_payment_intent(instruction=instruction)
        apply_payment_instruction_status(
            instruction,
            authorization_result.status,
            changed_by=request.user,
            note=authorization_result.status_reason,
            status_reason=authorization_result.status_reason,
            instruction_updates=authorization_result.instruction_updates,
        )
        instruction.refresh_from_db()
        return Response(TransferPaymentInstructionSerializer(instruction).data)


class TransferPaymentWebhookView(generics.GenericAPIView):
    serializer_class = PaymentWebhookEventCreateSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "webhook"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        provider_name = self.kwargs["provider_name"]
        try:
            get_payment_processor_by_provider(provider_name)
        except ValueError as exc:
            raise ValidationError({"provider_name": str(exc)}) from exc

        expected_secret = get_payment_webhook_secret(provider_name)
        secret_response = validate_webhook_secret(
            request,
            expected_secret=expected_secret,
            header_name="X-Payment-Webhook-Secret",
        )
        if secret_response is not None:
            return secret_response

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        webhook_event, created = TransferPaymentWebhookEvent.objects.get_or_create(
            provider_name=provider_name,
            provider_event_id=serializer.validated_data["event_id"],
            defaults={
                "event_type": serializer.validated_data["event_type"],
                "provider_reference": serializer.validated_data["provider_reference"],
                "payload": {
                    "amount": (
                        str(serializer.validated_data["amount"])
                        if serializer.validated_data.get("amount") is not None
                        else ""
                    ),
                    "currency_code": serializer.validated_data.get("currency_code", ""),
                    "status_reason": serializer.validated_data.get("status_reason", ""),
                    "metadata": serializer.validated_data.get("metadata", {}),
                    "payment_status": serializer.validated_data["payment_status"],
                },
                "event_created_at": serializer.validated_data.get("event_created_at"),
            },
        )

        if created:
            instruction_updates = {
                "last_webhook_metadata": serializer.validated_data.get("metadata", {}),
            }
            webhook_event = process_payment_webhook_event(
                webhook_event,
                payment_status=serializer.validated_data["payment_status"],
                status_reason=serializer.validated_data.get("status_reason", ""),
                instruction_updates=instruction_updates,
            )

        response_serializer = PaymentWebhookEventSerializer(webhook_event)
        return Response(
            {
                **response_serializer.data,
                "duplicate": not created,
            },
        )


class TransferPayoutWebhookView(generics.GenericAPIView):
    serializer_class = PayoutWebhookEventCreateSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "webhook"

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        provider_code = self.kwargs["provider_code"]
        expected_secret = get_payout_webhook_secret(provider_code)
        secret_response = validate_webhook_secret(
            request,
            expected_secret=expected_secret,
            header_name="X-Payout-Webhook-Secret",
        )
        if secret_response is not None:
            return secret_response

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            attempt = TransferPayoutAttempt.objects.select_related(
                "transfer",
                "provider",
                "currency",
            ).get(
                provider__code=provider_code,
                provider_reference=data["provider_reference"],
            )
        except TransferPayoutAttempt.DoesNotExist as exc:
            raise ValidationError(
                {"provider_reference": "Payout attempt not found."},
            ) from exc

        duplicate = bool(
            data["event_id"]
            and attempt.events.filter(provider_event_id=data["event_id"]).exists()
        )
        if not duplicate:
            attempt = sync_payout_attempt_status(
                attempt,
                target_status=data["payout_status"],
                provider_event_id=data["event_id"],
                provider_status=data.get("provider_status", ""),
                status_reason=data.get("status_reason", ""),
                metadata={
                    "webhook_metadata": data.get("metadata", {}),
                    "event_created_at": (
                        data.get("event_created_at").isoformat()
                        if data.get("event_created_at")
                        else ""
                    ),
                },
                note=(
                    f"Payout webhook received from {provider_code}."
                ),
            )

        return Response(
            {
                **TransferPayoutAttemptSerializer(attempt).data,
                "duplicate": duplicate,
            },
        )


class StaffTransferListView(generics.ListAPIView):
    serializer_class = StaffTransferSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        queryset = get_transfer_base_queryset()

        for query_param in (
            "status",
            "funding_status",
            "compliance_status",
            "payout_status",
        ):
            value = self.request.query_params.get(query_param, "").strip()
            if value:
                queryset = queryset.filter(**{query_param: value})

        search_term = self.request.query_params.get("q", "").strip()
        if search_term:
            queryset = queryset.filter(
                Q(reference__icontains=search_term)
                | Q(sender__email__icontains=search_term)
                | Q(recipient__first_name__icontains=search_term)
                | Q(recipient__last_name__icontains=search_term)
                | Q(recipient__phone_number__icontains=search_term),
            )

        return queryset[:100]


class StaffTransferReportView(generics.GenericAPIView):
    serializer_class = StaffReportQuerySerializer
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        start_at, end_at = make_report_window(
            serializer.validated_data.get("start_date"),
            serializer.validated_data.get("end_date"),
        )
        return Response(build_operations_report(start_at=start_at, end_at=end_at))


class StaffTransferExportView(generics.GenericAPIView):
    serializer_class = StaffExportQuerySerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = apply_staff_export_date_window(self.get_queryset(), serializer)

        status_filter = data.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        sender_email = data.get("sender_email", "").strip()
        if sender_email:
            queryset = queryset.filter(sender__email__icontains=sender_email)

        destination_country = data.get("destination_country", "").strip()
        if destination_country:
            queryset = queryset.filter(
                Q(destination_country__iso_code__iexact=destination_country)
                | Q(destination_country__name__icontains=destination_country),
            )

        search_term = data.get("q", "").strip()
        if search_term:
            queryset = queryset.filter(
                Q(reference__icontains=search_term)
                | Q(sender__email__icontains=search_term)
                | Q(recipient__first_name__icontains=search_term)
                | Q(recipient__last_name__icontains=search_term),
            )

        headers = [
            "transfer_id",
            "transfer_reference",
            "sender_email",
            "recipient_name",
            "source_country",
            "destination_country",
            "send_amount",
            "source_currency",
            "receive_amount",
            "destination_currency",
            "fee_amount",
            "status",
            "created_at",
            "updated_at",
        ]
        rows = (
            (
                transfer.id,
                transfer.reference,
                transfer.sender.email,
                recipient_full_name(transfer.recipient),
                transfer.source_country.name,
                transfer.destination_country.name,
                transfer.send_amount,
                transfer.source_currency.code,
                transfer.receive_amount,
                transfer.destination_currency.code,
                transfer.fee_amount,
                transfer.status,
                transfer.created_at,
                transfer.updated_at,
            )
            for transfer in queryset.order_by("-created_at")[:CSV_ROW_LIMIT]
        )
        return build_csv_response("mbongopay-transfers.csv", headers, rows)


class StaffComplianceExportView(generics.GenericAPIView):
    serializer_class = StaffExportQuerySerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return TransferComplianceEvent.objects.select_related(
            "transfer",
            "transfer__sender",
            "performed_by",
        )

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = apply_staff_export_date_window(self.get_queryset(), serializer)

        action_filter = data.get("action", "").strip()
        if action_filter:
            queryset = queryset.filter(action=action_filter)

        status_filter = data.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(
                Q(to_compliance_status=status_filter)
                | Q(transfer__compliance_status=status_filter)
                | Q(to_transfer_status=status_filter)
                | Q(transfer__status=status_filter),
            )

        sender_email = data.get("sender_email", "").strip()
        if sender_email:
            queryset = queryset.filter(transfer__sender__email__icontains=sender_email)

        destination_country = data.get("destination_country", "").strip()
        if destination_country:
            queryset = queryset.filter(
                Q(transfer__destination_country__iso_code__iexact=destination_country)
                | Q(transfer__destination_country__name__icontains=destination_country),
            )

        search_term = data.get("q", "").strip()
        if search_term:
            queryset = queryset.filter(
                Q(transfer__reference__icontains=search_term)
                | Q(transfer__sender__email__icontains=search_term)
                | Q(note__icontains=search_term)
                | Q(performed_by__email__icontains=search_term),
            )

        headers = [
            "event_id",
            "transfer_id",
            "transfer_reference",
            "sender_email",
            "action",
            "from_compliance_status",
            "to_compliance_status",
            "from_transfer_status",
            "to_transfer_status",
            "performed_by_email",
            "note",
            "created_at",
        ]
        rows = (
            (
                event.id,
                event.transfer.id,
                event.transfer.reference,
                event.transfer.sender.email,
                event.action,
                event.from_compliance_status,
                event.to_compliance_status,
                event.from_transfer_status,
                event.to_transfer_status,
                event.performed_by.email if event.performed_by else "",
                event.note,
                event.created_at,
            )
            for event in queryset.order_by("-created_at")[:CSV_ROW_LIMIT]
        )
        return build_csv_response("mbongopay-compliance-events.csv", headers, rows)


class StaffOperationalAuditExportView(generics.GenericAPIView):
    serializer_class = StaffExportQuerySerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return OperationalAuditLog.objects.select_related("actor")

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        queryset = apply_staff_export_date_window(self.get_queryset(), serializer)

        action_filter = data.get("action", "").strip()
        if action_filter:
            queryset = queryset.filter(action_name=action_filter)

        target_type = data.get("target_type", "").strip()
        if target_type:
            queryset = queryset.filter(target_type=target_type)

        status_filter = data.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(
                Q(previous_status=status_filter) | Q(new_status=status_filter),
            )

        search_term = data.get("q", "").strip()
        if search_term:
            queryset = queryset.filter(
                Q(actor__email__icontains=search_term)
                | Q(action_name__icontains=search_term)
                | Q(target_id__icontains=search_term)
                | Q(target_reference__icontains=search_term)
                | Q(note__icontains=search_term),
            )

        headers = [
            "audit_id",
            "actor_email",
            "action",
            "target_type",
            "target_id",
            "target_reference",
            "previous_status",
            "new_status",
            "note",
            "request_ip",
            "user_agent",
            "created_at",
        ]
        rows = (
            (
                audit_log.id,
                audit_log.actor.email if audit_log.actor else "",
                audit_log.action_name,
                audit_log.target_type,
                audit_log.target_id,
                audit_log.target_reference,
                audit_log.previous_status,
                audit_log.new_status,
                audit_log.note,
                audit_log.request_ip,
                audit_log.user_agent,
                audit_log.created_at,
            )
            for audit_log in queryset.order_by("-created_at")[:CSV_ROW_LIMIT]
        )
        return build_csv_response("mbongopay-operational-audit.csv", headers, rows)


class StaffTransferStatusTransitionView(generics.GenericAPIView):
    serializer_class = TransferStatusTransitionSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_status = transfer.status
        note = serializer.validated_data.get("note", "").strip()

        updated_transfer = transition_transfer_status(
            transfer,
            serializer.validated_data["status"],
            changed_by=request.user,
            note=note,
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_transfer.pk)
        record_transfer_operation_audit(
            request,
            action_name="transfer.status_transition",
            transfer=refreshed_transfer,
            previous_status=previous_status,
            new_status=refreshed_transfer.status,
            note=note,
            metadata={"requested_status": serializer.validated_data["status"]},
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferPaymentActionView(generics.GenericAPIView):
    serializer_class = TransferPaymentActionCreateSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_status = transfer.status

        payment_instruction = None
        payment_instruction_id = serializer.validated_data.get(
            "payment_instruction_id",
        )
        if payment_instruction_id:
            try:
                payment_instruction = transfer.payment_instructions.select_related(
                    "currency",
                ).get(id=payment_instruction_id)
            except TransferPaymentInstruction.DoesNotExist as exc:
                raise ValidationError(
                    {
                        "payment_instruction_id": (
                            "Payment instruction not found for this transfer."
                        ),
                    },
                ) from exc

        payment_action = create_payment_action(
            transfer,
            action=serializer.validated_data["action"],
            payment_instruction=payment_instruction,
            amount=serializer.validated_data.get("amount"),
            reason_code=serializer.validated_data.get("reason_code", ""),
            note=serializer.validated_data["note"],
            requested_by=request.user,
        )
        refreshed_transfer = self.get_queryset().get(pk=payment_action.transfer_id)
        record_transfer_operation_audit(
            request,
            action_name="transfer.payment_action",
            transfer=refreshed_transfer,
            target_type="transfer_payment_action",
            target_id=str(payment_action.id),
            previous_status=previous_status,
            new_status=refreshed_transfer.status,
            note=serializer.validated_data["note"],
            metadata={
                "payment_action": payment_action.action,
                "payment_action_status": payment_action.status,
                "payment_instruction_id": str(payment_action.payment_instruction_id),
            },
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferPayoutAttemptView(generics.GenericAPIView):
    serializer_class = TransferPayoutAttemptSubmitSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    def get(self, request, *args, **kwargs):
        transfer = self.get_object()
        attempts = transfer.payout_attempts.all()
        return Response(TransferPayoutAttemptSerializer(attempts, many=True).data)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_status = transfer.payout_status
        note = serializer.validated_data.get("note", "")

        attempt = submit_payout_for_transfer(
            transfer,
            changed_by=request.user,
            note=note,
        )
        refreshed_transfer = self.get_queryset().get(pk=attempt.transfer_id)
        record_transfer_operation_audit(
            request,
            action_name="transfer.payout_submit",
            transfer=refreshed_transfer,
            target_type="transfer_payout_attempt",
            target_id=str(attempt.id),
            previous_status=previous_status,
            new_status=refreshed_transfer.payout_status,
            note=note,
            metadata={"attempt_status": attempt.status},
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferPayoutStatusSyncView(generics.GenericAPIView):
    serializer_class = TransferPayoutStatusSyncSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    def get_payout_attempt(self, transfer):
        try:
            return transfer.payout_attempts.get(id=self.kwargs["attempt_id"])
        except TransferPayoutAttempt.DoesNotExist as exc:
            raise ValidationError(
                {"payout_attempt_id": "Payout attempt not found for this transfer."},
            ) from exc

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        attempt = self.get_payout_attempt(transfer)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_status = attempt.status

        updated_attempt = sync_payout_attempt_status(
            attempt,
            target_status=serializer.validated_data["payout_status"],
            provider_event_id=serializer.validated_data.get("provider_event_id", ""),
            provider_status=serializer.validated_data.get("provider_status", ""),
            status_reason=serializer.validated_data.get("status_reason", ""),
            metadata=serializer.validated_data.get("metadata", {}),
            changed_by=request.user,
            note=serializer.validated_data.get("status_reason", ""),
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_attempt.transfer_id)
        record_transfer_operation_audit(
            request,
            action_name="transfer.payout_status_sync",
            transfer=refreshed_transfer,
            target_type="transfer_payout_attempt",
            target_id=str(updated_attempt.id),
            previous_status=previous_status,
            new_status=updated_attempt.status,
            note=serializer.validated_data.get("status_reason", ""),
            metadata={
                "provider_event_id": serializer.validated_data.get(
                    "provider_event_id",
                    "",
                ),
            },
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferPayoutProviderSyncView(generics.GenericAPIView):
    serializer_class = TransferPayoutAttemptSubmitSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    def get_payout_attempt(self, transfer):
        try:
            return transfer.payout_attempts.get(id=self.kwargs["attempt_id"])
        except TransferPayoutAttempt.DoesNotExist as exc:
            raise ValidationError(
                {"payout_attempt_id": "Payout attempt not found for this transfer."},
            ) from exc

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        attempt = self.get_payout_attempt(transfer)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_status = attempt.status
        note = serializer.validated_data.get("note", "")

        updated_attempt = sync_payout_attempt_status_from_provider(
            attempt,
            changed_by=request.user,
            note=note,
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_attempt.transfer_id)
        record_transfer_operation_audit(
            request,
            action_name="transfer.payout_provider_sync",
            transfer=refreshed_transfer,
            target_type="transfer_payout_attempt",
            target_id=str(updated_attempt.id),
            previous_status=previous_status,
            new_status=updated_attempt.status,
            note=note,
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferPayoutRetryView(generics.GenericAPIView):
    serializer_class = TransferPayoutAttemptActionSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attempt = transfer.payout_attempts.get(id=self.kwargs["attempt_id"])
        except TransferPayoutAttempt.DoesNotExist as exc:
            raise ValidationError(
                {"payout_attempt_id": "Payout attempt not found for this transfer."},
            ) from exc
        previous_status = attempt.status

        updated_attempt = retry_payout_attempt(
            attempt,
            changed_by=request.user,
            note=serializer.validated_data["note"],
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_attempt.transfer_id)
        record_transfer_operation_audit(
            request,
            action_name="transfer.payout_retry",
            transfer=refreshed_transfer,
            target_type="transfer_payout_attempt",
            target_id=str(updated_attempt.id),
            previous_status=previous_status,
            new_status=updated_attempt.status,
            note=serializer.validated_data["note"],
            metadata={"retry_of": str(attempt.id)},
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferPayoutReverseView(generics.GenericAPIView):
    serializer_class = TransferPayoutAttemptActionSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            attempt = transfer.payout_attempts.get(id=self.kwargs["attempt_id"])
        except TransferPayoutAttempt.DoesNotExist as exc:
            raise ValidationError(
                {"payout_attempt_id": "Payout attempt not found for this transfer."},
            ) from exc
        previous_status = attempt.status

        updated_attempt = reverse_payout_attempt(
            attempt,
            changed_by=request.user,
            note=serializer.validated_data["note"],
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_attempt.transfer_id)
        record_transfer_operation_audit(
            request,
            action_name="transfer.payout_reverse",
            transfer=refreshed_transfer,
            target_type="transfer_payout_attempt",
            target_id=str(updated_attempt.id),
            previous_status=previous_status,
            new_status=updated_attempt.status,
            note=serializer.validated_data["note"],
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferComplianceActionView(generics.GenericAPIView):
    serializer_class = TransferComplianceActionSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous_status = transfer.compliance_status
        note = serializer.validated_data.get("note", "")

        updated_transfer = apply_compliance_action(
            transfer,
            serializer.validated_data["action"],
            performed_by=request.user,
            note=note,
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_transfer.pk)
        record_transfer_operation_audit(
            request,
            action_name="transfer.compliance_action",
            transfer=refreshed_transfer,
            previous_status=previous_status,
            new_status=refreshed_transfer.compliance_status,
            note=note,
            metadata={"compliance_action": serializer.validated_data["action"]},
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferSanctionsCheckReviewView(generics.GenericAPIView):
    serializer_class = TransferSanctionsCheckReviewSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            check = transfer.sanctions_checks.get(id=self.kwargs["check_id"])
        except TransferSanctionsCheck.DoesNotExist as exc:
            raise ValidationError(
                {"check_id": "Sanctions check not found for this transfer."},
            ) from exc
        previous_status = check.status
        note = serializer.validated_data.get("review_note", "")

        updated_transfer = review_transfer_sanctions_check(
            check,
            status=serializer.validated_data["status"],
            reviewed_by=request.user,
            review_note=serializer.validated_data.get("review_note", ""),
            provider_reference=serializer.validated_data.get("provider_reference", ""),
            match_score=serializer.validated_data.get("match_score"),
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_transfer.pk)
        record_transfer_operation_audit(
            request,
            action_name="transfer.sanctions_review",
            transfer=refreshed_transfer,
            target_type="transfer_sanctions_check",
            target_id=str(check.id),
            previous_status=previous_status,
            new_status=serializer.validated_data["status"],
            note=note,
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)


class StaffTransferAmlFlagReviewView(generics.GenericAPIView):
    serializer_class = TransferAmlFlagReviewSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return get_transfer_base_queryset()

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        transfer = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            flag = transfer.compliance_flags.get(
                id=self.kwargs["flag_id"],
                category=TransferComplianceFlag.Category.AML,
            )
        except TransferComplianceFlag.DoesNotExist as exc:
            raise ValidationError(
                {"flag_id": "AML flag not found for this transfer."},
            ) from exc
        previous_status = flag.status
        note = serializer.validated_data.get("review_note", "")

        updated_transfer = review_transfer_aml_flag(
            flag,
            decision=serializer.validated_data["decision"],
            reviewed_by=request.user,
            review_note=serializer.validated_data.get("review_note", ""),
            escalation_destination=serializer.validated_data.get(
                "escalation_destination",
                "",
            ),
            escalation_reference=serializer.validated_data.get(
                "escalation_reference",
                "",
            ),
        )
        refreshed_transfer = self.get_queryset().get(pk=updated_transfer.pk)
        flag.refresh_from_db()
        record_transfer_operation_audit(
            request,
            action_name="transfer.aml_flag_review",
            transfer=refreshed_transfer,
            target_type="transfer_compliance_flag",
            target_id=str(flag.id),
            previous_status=previous_status,
            new_status=flag.status,
            note=note,
            metadata={"decision": serializer.validated_data["decision"]},
        )
        return Response(StaffTransferSerializer(refreshed_transfer).data)
