from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    Transfer,
    TransferComplianceEvent,
    TransferComplianceFlag,
    TransferPaymentInstruction,
    TransferPaymentWebhookEvent,
    TransferStatusEvent,
)


ALLOWED_STATUS_TRANSITIONS = {
    Transfer.Status.AWAITING_FUNDING: {
        Transfer.Status.CANCELLED,
    },
    Transfer.Status.FUNDING_RECEIVED: {
        Transfer.Status.UNDER_REVIEW,
        Transfer.Status.CANCELLED,
        Transfer.Status.FAILED,
        Transfer.Status.REFUNDED,
    },
    Transfer.Status.UNDER_REVIEW: {
        Transfer.Status.APPROVED,
        Transfer.Status.REJECTED,
        Transfer.Status.FAILED,
    },
    Transfer.Status.APPROVED: {
        Transfer.Status.PROCESSING_PAYOUT,
        Transfer.Status.REJECTED,
        Transfer.Status.FAILED,
    },
    Transfer.Status.PROCESSING_PAYOUT: {
        Transfer.Status.PAID_OUT,
        Transfer.Status.FAILED,
    },
    Transfer.Status.PAID_OUT: {
        Transfer.Status.COMPLETED,
    },
    Transfer.Status.FAILED: {
        Transfer.Status.REFUNDED,
    },
    Transfer.Status.REJECTED: {
        Transfer.Status.REFUNDED,
    },
}


def get_allowed_status_transitions(transfer: Transfer) -> list[dict[str, str]]:
    allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(transfer.status, set())
    return [
        {"status": value, "label": label}
        for value, label in Transfer.Status.choices
        if value in allowed_targets
    ]


STATUS_SIDE_EFFECTS = {
    Transfer.Status.FUNDING_RECEIVED: {
        "funding_status": Transfer.FundingStatus.RECEIVED,
    },
    Transfer.Status.UNDER_REVIEW: {
        "funding_status": Transfer.FundingStatus.RECEIVED,
        "compliance_status": Transfer.ComplianceStatus.UNDER_REVIEW,
    },
    Transfer.Status.APPROVED: {
        "funding_status": Transfer.FundingStatus.RECEIVED,
        "compliance_status": Transfer.ComplianceStatus.APPROVED,
        "payout_status": Transfer.PayoutStatus.PENDING,
    },
    Transfer.Status.PROCESSING_PAYOUT: {
        "funding_status": Transfer.FundingStatus.RECEIVED,
        "compliance_status": Transfer.ComplianceStatus.APPROVED,
        "payout_status": Transfer.PayoutStatus.PROCESSING,
    },
    Transfer.Status.PAID_OUT: {
        "funding_status": Transfer.FundingStatus.RECEIVED,
        "compliance_status": Transfer.ComplianceStatus.APPROVED,
        "payout_status": Transfer.PayoutStatus.PAID,
    },
    Transfer.Status.COMPLETED: {
        "funding_status": Transfer.FundingStatus.RECEIVED,
        "compliance_status": Transfer.ComplianceStatus.APPROVED,
        "payout_status": Transfer.PayoutStatus.PAID,
    },
    Transfer.Status.REJECTED: {
        "compliance_status": Transfer.ComplianceStatus.REJECTED,
    },
    Transfer.Status.FAILED: {
        "payout_status": Transfer.PayoutStatus.FAILED,
    },
    Transfer.Status.REFUNDED: {
        "funding_status": Transfer.FundingStatus.REFUNDED,
    },
}


COMPLIANCE_ACTION_BY_STATUS = {
    Transfer.Status.UNDER_REVIEW: TransferComplianceEvent.Action.REVIEW,
    Transfer.Status.APPROVED: TransferComplianceEvent.Action.APPROVE,
    Transfer.Status.REJECTED: TransferComplianceEvent.Action.REJECT,
}


PAYMENT_PENDING_STATUSES = {
    TransferPaymentInstruction.Status.NOT_STARTED,
    TransferPaymentInstruction.Status.PENDING_AUTHORIZATION,
    TransferPaymentInstruction.Status.AUTHORIZED,
    TransferPaymentInstruction.Status.REQUIRES_REVIEW,
}


def validate_transition(transfer: Transfer, target_status: str) -> None:
    if target_status == transfer.status:
        raise serializers.ValidationError(
            {"status": "Transfer is already in this status."},
        )

    allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(transfer.status, set())
    if target_status not in allowed_targets:
        current_label = transfer.get_status_display()
        target_label = dict(Transfer.Status.choices).get(target_status, target_status)
        raise serializers.ValidationError(
            {"status": f"Cannot move from {current_label} to {target_label}."},
        )

    if (
        target_status == Transfer.Status.UNDER_REVIEW
        and transfer.funding_status != Transfer.FundingStatus.RECEIVED
    ):
        raise serializers.ValidationError(
            {"funding_status": "Funding must be received before review."},
        )

    if (
        target_status == Transfer.Status.PROCESSING_PAYOUT
        and transfer.compliance_status != Transfer.ComplianceStatus.APPROVED
    ):
        raise serializers.ValidationError(
            {"compliance_status": "Compliance must be approved before payout."},
        )


def record_compliance_event(
    transfer: Transfer,
    action: str,
    *,
    changed_by=None,
    note: str = "",
    previous_transfer_status: str = "",
    previous_compliance_status: str = "",
    metadata: dict | None = None,
) -> None:
    TransferComplianceEvent.objects.create(
        transfer=transfer,
        action=action,
        from_transfer_status=previous_transfer_status,
        to_transfer_status=transfer.status,
        from_compliance_status=previous_compliance_status,
        to_compliance_status=transfer.compliance_status,
        note=note,
        metadata=metadata or {},
        performed_by=changed_by,
    )


def update_manual_flag_statuses(
    transfer: Transfer,
    *,
    target_status: str,
    changed_by=None,
) -> None:
    open_flags = transfer.compliance_flags.filter(
        category=TransferComplianceFlag.Category.MANUAL,
        code="MANUAL_HOLD",
        status__in=(
            TransferComplianceFlag.Status.OPEN,
            TransferComplianceFlag.Status.ACKNOWLEDGED,
        ),
    )

    if target_status == Transfer.Status.UNDER_REVIEW:
        open_flags.update(
            status=TransferComplianceFlag.Status.ACKNOWLEDGED,
            updated_at=transfer.updated_at,
        )
        return

    if target_status in {Transfer.Status.APPROVED, Transfer.Status.REJECTED}:
        open_flags.update(
            status=TransferComplianceFlag.Status.RESOLVED,
            resolved_by=changed_by,
            resolved_at=transfer.updated_at,
            updated_at=transfer.updated_at,
        )


def get_funding_status_for_payment_status(payment_status: str) -> str:
    if payment_status == TransferPaymentInstruction.Status.PAID:
        return Transfer.FundingStatus.RECEIVED

    if payment_status in {
        TransferPaymentInstruction.Status.FAILED,
        TransferPaymentInstruction.Status.CANCELLED,
        TransferPaymentInstruction.Status.EXPIRED,
    }:
        return Transfer.FundingStatus.FAILED

    if payment_status in {
        TransferPaymentInstruction.Status.REVERSED,
        TransferPaymentInstruction.Status.REFUNDED,
    }:
        return Transfer.FundingStatus.REFUNDED

    return Transfer.FundingStatus.PENDING


@transaction.atomic
def apply_payment_instruction_status(
    instruction: TransferPaymentInstruction,
    target_status: str,
    *,
    changed_by=None,
    note: str = "",
    status_reason: str = "",
    instruction_updates: dict | None = None,
) -> Transfer:
    is_same_status = target_status == instruction.status
    if is_same_status and not status_reason and not instruction_updates:
        return instruction.transfer

    now = timezone.now()
    previous_transfer_status = instruction.transfer.status
    instruction.status = target_status
    if status_reason:
        instruction.status_reason = status_reason
    if instruction_updates:
        instruction.instructions = {
            **instruction.instructions,
            **instruction_updates,
        }

    if not is_same_status and target_status == TransferPaymentInstruction.Status.AUTHORIZED:
        instruction.authorized_at = now
    elif not is_same_status and target_status == TransferPaymentInstruction.Status.PAID:
        instruction.completed_at = now
    elif not is_same_status and target_status in {
        TransferPaymentInstruction.Status.FAILED,
        TransferPaymentInstruction.Status.CANCELLED,
        TransferPaymentInstruction.Status.EXPIRED,
    }:
        instruction.failed_at = now
    elif not is_same_status and target_status == TransferPaymentInstruction.Status.REVERSED:
        instruction.reversed_at = now
    elif not is_same_status and target_status == TransferPaymentInstruction.Status.REFUNDED:
        instruction.refunded_at = now

    instruction.save(
        update_fields=(
            "status",
            "status_reason",
            "instructions",
            "authorized_at",
            "completed_at",
            "failed_at",
            "reversed_at",
            "refunded_at",
            "updated_at",
        ),
    )

    transfer = instruction.transfer
    transfer.funding_status = get_funding_status_for_payment_status(target_status)

    if (
        target_status == TransferPaymentInstruction.Status.PAID
        and transfer.status == Transfer.Status.AWAITING_FUNDING
    ):
        transfer.status = Transfer.Status.FUNDING_RECEIVED
    elif target_status in {
        TransferPaymentInstruction.Status.REVERSED,
        TransferPaymentInstruction.Status.REFUNDED,
    } and transfer.status not in {
        Transfer.Status.CANCELLED,
        Transfer.Status.REJECTED,
        Transfer.Status.REFUNDED,
    }:
        transfer.status = Transfer.Status.REFUNDED

    transfer.save(update_fields=("status", "funding_status", "updated_at"))

    if transfer.status != previous_transfer_status:
        TransferStatusEvent.objects.create(
            transfer=transfer,
            from_status=previous_transfer_status,
            to_status=transfer.status,
            changed_by=changed_by,
            note=note or f"Payment marked {instruction.get_status_display().lower()}.",
        )

    return transfer


@transaction.atomic
def process_payment_webhook_event(
    webhook_event: TransferPaymentWebhookEvent,
    *,
    payment_status: str,
    status_reason: str = "",
    instruction_updates: dict | None = None,
) -> TransferPaymentWebhookEvent:
    try:
        instruction = (
            TransferPaymentInstruction.objects.select_related("transfer", "currency")
            .select_for_update()
            .get(
                provider_name=webhook_event.provider_name,
                provider_reference=webhook_event.provider_reference,
            )
        )
    except TransferPaymentInstruction.DoesNotExist:
        webhook_event.processing_status = (
            TransferPaymentWebhookEvent.ProcessingStatus.IGNORED
        )
        webhook_event.processing_message = "Payment instruction not found."
        webhook_event.processed_at = timezone.now()
        webhook_event.save(
            update_fields=(
                "processing_status",
                "processing_message",
                "processed_at",
                "updated_at",
            ),
        )
        return webhook_event

    if webhook_event.payload.get("amount"):
        payload_amount = str(webhook_event.payload["amount"])
        if payload_amount != str(instruction.amount):
            webhook_event.payment_instruction = instruction
            webhook_event.processing_status = (
                TransferPaymentWebhookEvent.ProcessingStatus.FAILED
            )
            webhook_event.processing_message = "Webhook amount did not match instruction."
            webhook_event.processed_at = timezone.now()
            webhook_event.save(
                update_fields=(
                    "payment_instruction",
                    "processing_status",
                    "processing_message",
                    "processed_at",
                    "updated_at",
                ),
            )
            return webhook_event

    if webhook_event.payload.get("currency_code"):
        payload_currency = str(webhook_event.payload["currency_code"]).upper()
        if payload_currency != instruction.currency.code.upper():
            webhook_event.payment_instruction = instruction
            webhook_event.processing_status = (
                TransferPaymentWebhookEvent.ProcessingStatus.FAILED
            )
            webhook_event.processing_message = (
                "Webhook currency did not match instruction."
            )
            webhook_event.processed_at = timezone.now()
            webhook_event.save(
                update_fields=(
                    "payment_instruction",
                    "processing_status",
                    "processing_message",
                    "processed_at",
                    "updated_at",
                ),
            )
            return webhook_event

    apply_payment_instruction_status(
        instruction,
        payment_status,
        note=(
            f"Webhook {webhook_event.event_type} received from "
            f"{webhook_event.provider_name}."
        ),
        status_reason=status_reason,
        instruction_updates={
            "last_webhook_event_id": webhook_event.provider_event_id,
            "last_webhook_event_type": webhook_event.event_type,
            "last_webhook_status": payment_status,
            **(instruction_updates or {}),
        },
    )
    instruction.refresh_from_db()
    webhook_event.payment_instruction = instruction
    webhook_event.processing_status = (
        TransferPaymentWebhookEvent.ProcessingStatus.PROCESSED
    )
    webhook_event.processing_message = (
        status_reason or f"Payment updated to {instruction.get_status_display().lower()}."
    )
    webhook_event.resulting_payment_status = instruction.status
    webhook_event.processed_at = timezone.now()
    webhook_event.save(
        update_fields=(
            "payment_instruction",
            "processing_status",
            "processing_message",
            "resulting_payment_status",
            "processed_at",
            "updated_at",
        ),
    )
    return webhook_event


@transaction.atomic
def transition_transfer_status(
    transfer: Transfer,
    target_status: str,
    *,
    changed_by=None,
    note: str = "",
) -> Transfer:
    validate_transition(transfer, target_status)

    previous_status = transfer.status
    previous_compliance_status = transfer.compliance_status
    transfer.status = target_status

    for field, value in STATUS_SIDE_EFFECTS.get(target_status, {}).items():
        setattr(transfer, field, value)

    transfer.save(
        update_fields=(
            "status",
            "funding_status",
            "compliance_status",
            "payout_status",
            "updated_at",
        ),
    )
    TransferStatusEvent.objects.create(
        transfer=transfer,
        from_status=previous_status,
        to_status=target_status,
        changed_by=changed_by,
        note=note,
    )

    update_manual_flag_statuses(
        transfer,
        target_status=target_status,
        changed_by=changed_by,
    )

    compliance_action = COMPLIANCE_ACTION_BY_STATUS.get(target_status)
    if compliance_action:
        record_compliance_event(
            transfer,
            compliance_action,
            changed_by=changed_by,
            note=note,
            previous_transfer_status=previous_status,
            previous_compliance_status=previous_compliance_status,
        )
    return transfer
