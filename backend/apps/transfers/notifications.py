from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import (
    Transfer,
    TransferComplianceEvent,
    TransferComplianceFlag,
    TransferNotification,
    TransferPaymentInstruction,
    TransferPayoutAttempt,
    TransferPayoutEvent,
    TransferStatusEvent,
)


PAYMENT_FAILURE_STATUSES = {
    TransferPaymentInstruction.Status.FAILED,
    TransferPaymentInstruction.Status.CANCELLED,
    TransferPaymentInstruction.Status.EXPIRED,
    TransferPaymentInstruction.Status.REVERSED,
    TransferPaymentInstruction.Status.REFUNDED,
}

TRANSFER_FAILURE_STATUSES = {
    Transfer.Status.CANCELLED,
    Transfer.Status.FAILED,
    Transfer.Status.REJECTED,
    Transfer.Status.REFUNDED,
}

PAYOUT_FAILURE_STATUSES = {
    TransferPayoutAttempt.Status.FAILED,
    TransferPayoutAttempt.Status.REVERSED,
}


def format_money(amount: Decimal, currency_code: str) -> str:
    return f"{amount:,.2f} {currency_code}"


def sender_name(transfer: Transfer) -> str:
    name = f"{transfer.sender.first_name} {transfer.sender.last_name}".strip()
    return name or transfer.sender.email


def recipient_name(transfer: Transfer) -> str:
    return f"{transfer.recipient.first_name} {transfer.recipient.last_name}".strip()


def transfer_url(transfer: Transfer) -> str:
    return f"{settings.FRONTEND_BASE_URL}/transfers/{transfer.id}"


def trigger_identity(trigger) -> tuple[str, str]:
    if trigger is None:
        return "transfer", str("")

    return (
        f"{trigger._meta.app_label}.{trigger._meta.model_name}",
        str(trigger.pk),
    )


def build_dedupe_key(
    *,
    channel: str,
    event_type: str,
    transfer: Transfer,
    trigger=None,
    suffix: str = "",
) -> str:
    trigger_model, trigger_id = trigger_identity(trigger)
    trigger_part = f"{trigger_model}:{trigger_id or transfer.pk}"
    if suffix:
        trigger_part = f"{trigger_part}:{suffix}"
    return f"{channel}:{event_type}:{transfer.pk}:{trigger_part}"


def queue_email_notification(
    *,
    transfer: Transfer,
    event_type: str,
    subject: str,
    body: str,
    trigger=None,
    metadata: dict | None = None,
    dedupe_suffix: str = "",
) -> TransferNotification | None:
    recipient_email = transfer.sender.email.strip()
    if not recipient_email:
        return None

    trigger_model, trigger_id = trigger_identity(trigger)
    dedupe_key = build_dedupe_key(
        channel=TransferNotification.Channel.EMAIL,
        event_type=event_type,
        transfer=transfer,
        trigger=trigger,
        suffix=dedupe_suffix,
    )
    notification, created = TransferNotification.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "transfer": transfer,
            "channel": TransferNotification.Channel.EMAIL,
            "event_type": event_type,
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "trigger_model": trigger_model,
            "trigger_id": trigger_id,
            "metadata": metadata or {},
        },
    )

    if created:
        transaction.on_commit(lambda: deliver_email_notification(notification.id))

    return notification


def deliver_email_notification(notification_id) -> None:
    notification = TransferNotification.objects.get(id=notification_id)
    if notification.channel != TransferNotification.Channel.EMAIL:
        notification.status = TransferNotification.Status.SKIPPED
        notification.error = "SMS delivery is deferred."
        notification.save(update_fields=("status", "error", "updated_at"))
        return

    if notification.status == TransferNotification.Status.SENT:
        return

    notification.attempts += 1
    try:
        send_mail(
            notification.subject,
            notification.body,
            settings.DEFAULT_FROM_EMAIL,
            [notification.recipient_email],
            fail_silently=False,
        )
    except Exception as exc:  # pragma: no cover - backend-specific delivery failure
        notification.status = TransferNotification.Status.FAILED
        notification.error = str(exc)
        notification.save(
            update_fields=("attempts", "status", "error", "updated_at"),
        )
        return

    notification.status = TransferNotification.Status.SENT
    notification.sent_at = timezone.now()
    notification.error = ""
    notification.save(
        update_fields=("attempts", "status", "sent_at", "error", "updated_at"),
    )


def base_transfer_lines(transfer: Transfer) -> list[str]:
    return [
        f"Transfer reference: {transfer.reference}",
        f"Sender: {sender_name(transfer)}",
        f"Recipient: {recipient_name(transfer)}",
        (
            "Send amount: "
            f"{format_money(transfer.send_amount, transfer.source_currency.code)}"
        ),
        (
            "Recipient receives: "
            f"{format_money(transfer.receive_amount, transfer.destination_currency.code)}"
        ),
        f"Status: {transfer.get_status_display()}",
        f"Track this transfer: {transfer_url(transfer)}",
    ]


def notify_transfer_created(
    transfer: Transfer,
    *,
    status_event: TransferStatusEvent | None = None,
) -> None:
    subject = f"MbongoPay transfer {transfer.reference} created"
    body = "\n".join(
        [
            f"Hi {sender_name(transfer)},",
            "",
            "Your MbongoPay transfer has been created and is awaiting payment.",
            "",
            *base_transfer_lines(transfer),
            "",
            "We will email you as the payment and payout move forward.",
        ],
    )
    queue_email_notification(
        transfer=transfer,
        event_type=TransferNotification.EventType.TRANSFER_CREATED,
        subject=subject,
        body=body,
        trigger=status_event or transfer,
        metadata={"status": transfer.status},
    )


def notify_payment_received(
    transfer: Transfer,
    *,
    instruction: TransferPaymentInstruction | None = None,
    status_event: TransferStatusEvent | None = None,
    note: str = "",
) -> None:
    trigger = instruction or status_event or transfer
    total_amount = transfer.send_amount + transfer.fee_amount
    payment_method = (
        instruction.get_payment_method_display()
        if instruction
        else "payment"
    )
    body = "\n".join(
        [
            f"Hi {sender_name(transfer)},",
            "",
            f"We received your {payment_method.lower()} for transfer {transfer.reference}.",
            (
                "Total paid: "
                f"{format_money(total_amount, transfer.source_currency.code)}"
            ),
            "",
            *base_transfer_lines(transfer),
        ],
    )
    queue_email_notification(
        transfer=transfer,
        event_type=TransferNotification.EventType.PAYMENT_RECEIVED,
        subject=f"Payment received for transfer {transfer.reference}",
        body=body,
        trigger=trigger,
        metadata={
            "payment_instruction_id": str(instruction.id) if instruction else "",
            "payment_method": instruction.payment_method if instruction else "",
            "note": note,
        },
    )
    notify_receipt_email(
        transfer,
        instruction=instruction,
        trigger=trigger,
    )


def notify_receipt_email(
    transfer: Transfer,
    *,
    instruction: TransferPaymentInstruction | None = None,
    trigger=None,
) -> None:
    total_amount = transfer.send_amount + transfer.fee_amount
    receipt_lines = [
        f"Receipt for transfer {transfer.reference}",
        "",
        f"Paid by: {sender_name(transfer)}",
        f"Payment method: {instruction.get_payment_method_display() if instruction else 'Payment'}",
        f"Send amount: {format_money(transfer.send_amount, transfer.source_currency.code)}",
        f"Fee: {format_money(transfer.fee_amount, transfer.source_currency.code)}",
        f"Total paid: {format_money(total_amount, transfer.source_currency.code)}",
        f"Exchange rate: 1 {transfer.source_currency.code} = {transfer.exchange_rate} {transfer.destination_currency.code}",
        f"Recipient receives: {format_money(transfer.receive_amount, transfer.destination_currency.code)}",
        f"Recipient: {recipient_name(transfer)}",
        "",
        f"View transfer: {transfer_url(transfer)}",
    ]
    queue_email_notification(
        transfer=transfer,
        event_type=TransferNotification.EventType.RECEIPT,
        subject=f"Receipt for MbongoPay transfer {transfer.reference}",
        body="\n".join(receipt_lines),
        trigger=trigger or instruction or transfer,
        metadata={
            "payment_instruction_id": str(instruction.id) if instruction else "",
            "total_paid": str(total_amount),
            "currency": transfer.source_currency.code,
        },
        dedupe_suffix="receipt",
    )


def notify_payout_complete(
    attempt: TransferPayoutAttempt,
    *,
    payout_event: TransferPayoutEvent | None = None,
) -> None:
    transfer = attempt.transfer
    body = "\n".join(
        [
            f"Hi {sender_name(transfer)},",
            "",
            f"The payout for transfer {transfer.reference} is complete.",
            (
                f"{recipient_name(transfer)} received "
                f"{format_money(attempt.amount, attempt.currency.code)}."
            ),
            "",
            *base_transfer_lines(transfer),
        ],
    )
    queue_email_notification(
        transfer=transfer,
        event_type=TransferNotification.EventType.PAYOUT_COMPLETE,
        subject=f"Payout complete for transfer {transfer.reference}",
        body=body,
        trigger=payout_event or attempt,
        metadata={
            "payout_attempt_id": str(attempt.id),
            "provider_reference": attempt.provider_reference,
            "payout_status": attempt.status,
        },
    )


def notify_transaction_failed(
    transfer: Transfer,
    *,
    trigger=None,
    reason: str = "",
    status_value: str = "",
) -> None:
    failure_reason = reason or "The transaction could not be completed."
    body = "\n".join(
        [
            f"Hi {sender_name(transfer)},",
            "",
            f"We could not complete transfer {transfer.reference}.",
            f"Reason: {failure_reason}",
            "",
            *base_transfer_lines(transfer),
            "",
            "You can review the transfer or contact support from your account.",
        ],
    )
    queue_email_notification(
        transfer=transfer,
        event_type=TransferNotification.EventType.TRANSACTION_FAILED,
        subject=f"Action needed for transfer {transfer.reference}",
        body=body,
        trigger=trigger or transfer,
        metadata={
            "status": status_value or transfer.status,
            "reason": failure_reason,
        },
    )


def is_verification_alert_flag(flag: TransferComplianceFlag) -> bool:
    if flag.category == TransferComplianceFlag.Category.RECIPIENT:
        return True

    if flag.category == TransferComplianceFlag.Category.RISK_RULE:
        return flag.metadata.get("rule_type") in {
            "incomplete_profile",
            "unverified_kyc",
        } or flag.metadata.get("action") == "hold"

    if flag.category in {
        TransferComplianceFlag.Category.PAYMENT,
        TransferComplianceFlag.Category.MANUAL,
        TransferComplianceFlag.Category.SANCTIONS,
        TransferComplianceFlag.Category.AML,
    }:
        return True

    return flag.metadata.get("action") == "hold"


def get_verification_alert_flags(
    transfer: Transfer,
    flags: Iterable[TransferComplianceFlag] | None = None,
) -> list[TransferComplianceFlag]:
    if flags is None:
        flags = transfer.compliance_flags.filter(
            status__in=(
                TransferComplianceFlag.Status.OPEN,
                TransferComplianceFlag.Status.ACKNOWLEDGED,
            ),
        )

    return [flag for flag in flags if is_verification_alert_flag(flag)]


def notify_verification_required(
    transfer: Transfer,
    *,
    flags: Iterable[TransferComplianceFlag] | None = None,
    compliance_event: TransferComplianceEvent | None = None,
    note: str = "",
) -> None:
    alert_flags = get_verification_alert_flags(transfer, flags)
    if not alert_flags and transfer.compliance_status not in {
        Transfer.ComplianceStatus.ON_HOLD,
        Transfer.ComplianceStatus.NEEDS_MORE_INFO,
    }:
        return

    trigger = compliance_event or (alert_flags[0] if alert_flags else transfer)
    flag_lines = [
        f"- {flag.title}: {flag.description or flag.get_category_display()}"
        for flag in alert_flags[:5]
    ]
    if not flag_lines:
        flag_lines = ["- Additional information is required before this transfer proceeds."]

    body = "\n".join(
        [
            f"Hi {sender_name(transfer)},",
            "",
            f"Transfer {transfer.reference} requires verification or additional review.",
            "",
            *flag_lines,
            "",
            *base_transfer_lines(transfer),
            "",
            "Open your account to review the next steps.",
        ],
    )
    queue_email_notification(
        transfer=transfer,
        event_type=TransferNotification.EventType.VERIFICATION_REQUIRED,
        subject=f"Verification required for transfer {transfer.reference}",
        body=body,
        trigger=trigger,
        metadata={
            "compliance_status": transfer.compliance_status,
            "flag_ids": [str(flag.id) for flag in alert_flags],
            "note": note,
        },
    )


def notify_for_compliance_event(event: TransferComplianceEvent) -> None:
    if event.to_compliance_status in {
        Transfer.ComplianceStatus.ON_HOLD,
        Transfer.ComplianceStatus.NEEDS_MORE_INFO,
    }:
        notify_verification_required(
            event.transfer,
            compliance_event=event,
            note=event.note,
        )
