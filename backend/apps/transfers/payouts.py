from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import serializers

from apps.countries.services import select_payout_provider
from apps.quotes.services import get_active_corridor

from .models import (
    Transfer,
    TransferPayoutAttempt,
    TransferPayoutEvent,
    TransferStatusEvent,
)
from .notifications import (
    PAYOUT_FAILURE_STATUSES,
    notify_payout_complete,
    notify_transaction_failed,
)
from .payout_providers import get_payout_processor


TERMINAL_PAYOUT_ATTEMPT_STATUSES = {
    TransferPayoutAttempt.Status.PAID_OUT,
    TransferPayoutAttempt.Status.FAILED,
    TransferPayoutAttempt.Status.REVERSED,
}

TRANSFER_PAYOUT_STATUS_BY_ATTEMPT_STATUS = {
    TransferPayoutAttempt.Status.QUEUED: Transfer.PayoutStatus.QUEUED,
    TransferPayoutAttempt.Status.SUBMITTED: Transfer.PayoutStatus.SUBMITTED,
    TransferPayoutAttempt.Status.PROCESSING: Transfer.PayoutStatus.PROCESSING,
    TransferPayoutAttempt.Status.PAID_OUT: Transfer.PayoutStatus.PAID_OUT,
    TransferPayoutAttempt.Status.FAILED: Transfer.PayoutStatus.FAILED,
    TransferPayoutAttempt.Status.REVERSED: Transfer.PayoutStatus.REVERSED,
    TransferPayoutAttempt.Status.RETRYING: Transfer.PayoutStatus.RETRYING,
}

PAYOUT_EVENT_ACTION_BY_ATTEMPT_STATUS = {
    TransferPayoutAttempt.Status.SUBMITTED: TransferPayoutEvent.Action.SUBMIT,
    TransferPayoutAttempt.Status.FAILED: TransferPayoutEvent.Action.FAIL,
    TransferPayoutAttempt.Status.REVERSED: TransferPayoutEvent.Action.REVERSE,
}


def get_latest_payout_attempt(transfer: Transfer) -> TransferPayoutAttempt | None:
    return transfer.payout_attempts.select_related("provider", "currency").first()


def ensure_transfer_has_payout_provider(transfer: Transfer) -> None:
    if transfer.payout_provider_id:
        return

    corridor = get_active_corridor(
        transfer.source_country_id,
        transfer.destination_country_id,
    )
    provider_selection = select_payout_provider(
        corridor,
        transfer.payout_method,
        transfer.send_amount,
    )
    transfer.payout_provider = provider_selection.provider
    transfer.save(update_fields=("payout_provider", "updated_at"))


def validate_transfer_ready_for_payout(transfer: Transfer) -> None:
    if transfer.funding_status != Transfer.FundingStatus.RECEIVED:
        raise serializers.ValidationError(
            {"funding_status": "Funding must be received before payout."},
        )

    if transfer.compliance_status != Transfer.ComplianceStatus.APPROVED:
        raise serializers.ValidationError(
            {"compliance_status": "Compliance must be approved before payout."},
        )

    if transfer.status not in {
        Transfer.Status.APPROVED,
        Transfer.Status.PROCESSING_PAYOUT,
        Transfer.Status.FAILED,
    }:
        raise serializers.ValidationError(
            {"status": "Payout can only be submitted after transfer approval."},
        )

    ensure_transfer_has_payout_provider(transfer)

    if transfer.payout_provider.payout_method != transfer.payout_method:
        raise serializers.ValidationError(
            {"payout_provider": "Selected provider does not support this payout method."},
        )


def build_destination_snapshot(transfer: Transfer) -> dict:
    snapshot = {
        "recipient_id": str(transfer.recipient_id),
        "recipient_name": (
            f"{transfer.recipient.first_name} {transfer.recipient.last_name}"
        ).strip(),
        "recipient_country": transfer.destination_country.iso_code,
        "payout_method": transfer.payout_method,
    }

    if transfer.payout_method == "mobile_money":
        account = (
            transfer.recipient.mobile_money_accounts.filter(is_default=True).first()
            or transfer.recipient.mobile_money_accounts.first()
        )
        if account:
            snapshot["mobile_money"] = {
                "provider_name": account.provider_name,
                "mobile_number": account.mobile_number,
                "account_name": account.account_name,
            }

    if transfer.payout_method == "bank_deposit":
        account = (
            transfer.recipient.bank_accounts.filter(is_default=True).first()
            or transfer.recipient.bank_accounts.first()
        )
        if account:
            snapshot["bank_account"] = {
                "bank_name": account.bank_name,
                "account_number": account.account_number,
                "account_name": account.account_name,
                "branch_name": account.branch_name,
                "swift_code": account.swift_code,
            }

    return snapshot


def get_next_attempt_number(transfer: Transfer) -> int:
    current_max = transfer.payout_attempts.aggregate(
        max_attempt=Max("attempt_number"),
    )["max_attempt"]
    return (current_max or 0) + 1


def record_payout_event(
    *,
    transfer: Transfer,
    payout_attempt: TransferPayoutAttempt | None,
    action: str,
    from_payout_status: str,
    to_payout_status: str,
    changed_by=None,
    note: str = "",
    provider_event_id: str = "",
    metadata: dict | None = None,
) -> TransferPayoutEvent | None:
    provider_event_id = provider_event_id.strip()
    if provider_event_id and payout_attempt:
        existing_event = TransferPayoutEvent.objects.filter(
            payout_attempt=payout_attempt,
            provider_event_id=provider_event_id,
        ).first()
        if existing_event:
            return None

    return TransferPayoutEvent.objects.create(
        transfer=transfer,
        payout_attempt=payout_attempt,
        action=action,
        from_payout_status=from_payout_status,
        to_payout_status=to_payout_status,
        provider_event_id=provider_event_id,
        note=note,
        metadata=metadata or {},
        performed_by=changed_by,
    )


def update_transfer_for_payout_status(
    transfer: Transfer,
    target_status: str,
    *,
    changed_by=None,
    note: str = "",
) -> None:
    previous_transfer_status = transfer.status
    transfer.payout_status = TRANSFER_PAYOUT_STATUS_BY_ATTEMPT_STATUS[target_status]

    if target_status in {
        TransferPayoutAttempt.Status.SUBMITTED,
        TransferPayoutAttempt.Status.PROCESSING,
        TransferPayoutAttempt.Status.RETRYING,
    }:
        transfer.status = Transfer.Status.PROCESSING_PAYOUT
    elif target_status == TransferPayoutAttempt.Status.PAID_OUT:
        if transfer.status != Transfer.Status.COMPLETED:
            transfer.status = Transfer.Status.PAID_OUT
    elif target_status in {
        TransferPayoutAttempt.Status.FAILED,
        TransferPayoutAttempt.Status.REVERSED,
    }:
        transfer.status = Transfer.Status.FAILED

    transfer.save(update_fields=("status", "payout_status", "updated_at"))

    if previous_transfer_status != transfer.status:
        TransferStatusEvent.objects.create(
            transfer=transfer,
            from_status=previous_transfer_status,
            to_status=transfer.status,
            changed_by=changed_by,
            note=note,
        )


@transaction.atomic
def apply_payout_attempt_status(
    attempt: TransferPayoutAttempt,
    target_status: str,
    *,
    changed_by=None,
    note: str = "",
    provider_event_id: str = "",
    provider_status: str = "",
    status_reason: str = "",
    response_payload: dict | None = None,
    action: str | None = None,
) -> TransferPayoutAttempt:
    if target_status not in TransferPayoutAttempt.Status.values:
        raise serializers.ValidationError({"payout_status": "Unsupported payout status."})

    if provider_event_id and TransferPayoutEvent.objects.filter(
        payout_attempt=attempt,
        provider_event_id=provider_event_id.strip(),
    ).exists():
        return attempt

    now = timezone.now()
    previous_status = attempt.status
    attempt.status = target_status

    if provider_status:
        attempt.provider_status = provider_status
    if status_reason:
        attempt.status_reason = status_reason
    if response_payload:
        attempt.response_payload = {
            **attempt.response_payload,
            **response_payload,
        }

    if target_status in {
        TransferPayoutAttempt.Status.SUBMITTED,
        TransferPayoutAttempt.Status.PROCESSING,
    } and not attempt.submitted_at:
        attempt.submitted_at = now
    elif target_status == TransferPayoutAttempt.Status.PAID_OUT:
        attempt.completed_at = now
    elif target_status == TransferPayoutAttempt.Status.FAILED:
        attempt.failed_at = now
    elif target_status == TransferPayoutAttempt.Status.REVERSED:
        attempt.reversed_at = now

    attempt.save(
        update_fields=(
            "status",
            "provider_status",
            "status_reason",
            "response_payload",
            "submitted_at",
            "completed_at",
            "failed_at",
            "reversed_at",
            "updated_at",
        ),
    )

    transfer = attempt.transfer
    update_transfer_for_payout_status(
        transfer,
        target_status,
        changed_by=changed_by,
        note=note or f"Payout marked {attempt.get_status_display().lower()}.",
    )

    event_action = action or PAYOUT_EVENT_ACTION_BY_ATTEMPT_STATUS.get(
        target_status,
        TransferPayoutEvent.Action.STATUS_SYNC,
    )
    payout_event = record_payout_event(
        transfer=transfer,
        payout_attempt=attempt,
        action=event_action,
        from_payout_status=previous_status,
        to_payout_status=target_status,
        changed_by=changed_by,
        note=note or status_reason,
        provider_event_id=provider_event_id,
        metadata={
            "provider_status": provider_status,
            "status_reason": status_reason,
            **(response_payload or {}),
        },
    )
    if target_status != previous_status and payout_event:
        if target_status == TransferPayoutAttempt.Status.PAID_OUT:
            notify_payout_complete(attempt, payout_event=payout_event)
        elif target_status in PAYOUT_FAILURE_STATUSES:
            notify_transaction_failed(
                transfer,
                trigger=payout_event,
                reason=status_reason or note,
                status_value=target_status,
            )
    attempt.refresh_from_db()
    return attempt


@transaction.atomic
def submit_payout_for_transfer(
    transfer: Transfer,
    *,
    changed_by=None,
    note: str = "",
    retry_of: TransferPayoutAttempt | None = None,
) -> TransferPayoutAttempt:
    transfer = (
        Transfer.objects.select_related(
            "recipient",
            "source_country",
            "destination_country",
            "destination_currency",
        )
        .prefetch_related(
            "recipient__mobile_money_accounts",
            "recipient__bank_accounts",
        )
        .select_for_update()
        .get(id=transfer.id)
    )
    validate_transfer_ready_for_payout(transfer)

    active_attempt = (
        transfer.payout_attempts.exclude(status__in=TERMINAL_PAYOUT_ATTEMPT_STATUSES)
        .select_related("provider", "currency")
        .order_by("-attempt_number")
        .first()
    )
    if active_attempt and retry_of is None:
        return active_attempt

    attempt = TransferPayoutAttempt.objects.create(
        transfer=transfer,
        retry_of=retry_of,
        provider=transfer.payout_provider,
        payout_method=transfer.payout_method,
        attempt_number=get_next_attempt_number(transfer),
        amount=transfer.receive_amount,
        currency=transfer.destination_currency,
        destination_snapshot=build_destination_snapshot(transfer),
        created_by=changed_by,
    )

    processor = get_payout_processor(
        transfer.payout_provider.code,
        provider=transfer.payout_provider,
    )
    result = processor.submit_payout(transfer=transfer, attempt=attempt)
    attempt.request_payload = result.request_payload
    attempt.response_payload = result.response_payload
    attempt.save(update_fields=("request_payload", "response_payload", "updated_at"))

    return apply_payout_attempt_status(
        attempt,
        result.status,
        changed_by=changed_by,
        note=note or result.status_reason,
        provider_status=result.provider_status,
        status_reason=result.status_reason,
        response_payload=result.response_payload,
        action=TransferPayoutEvent.Action.SUBMIT,
    )


@transaction.atomic
def sync_payout_attempt_status(
    attempt: TransferPayoutAttempt,
    *,
    target_status: str,
    changed_by=None,
    note: str = "",
    provider_event_id: str = "",
    provider_status: str = "",
    status_reason: str = "",
    metadata: dict | None = None,
) -> TransferPayoutAttempt:
    return apply_payout_attempt_status(
        attempt,
        target_status,
        changed_by=changed_by,
        note=note,
        provider_event_id=provider_event_id,
        provider_status=provider_status,
        status_reason=status_reason,
        response_payload=metadata or {},
        action=TransferPayoutEvent.Action.STATUS_SYNC,
    )


@transaction.atomic
def sync_payout_attempt_status_from_provider(
    attempt: TransferPayoutAttempt,
    *,
    changed_by=None,
    note: str = "",
) -> TransferPayoutAttempt:
    if attempt.is_terminal:
        return attempt

    processor = get_payout_processor(attempt.provider.code, provider=attempt.provider)
    result = processor.get_payout_status(attempt=attempt)
    return apply_payout_attempt_status(
        attempt,
        result.status,
        changed_by=changed_by,
        note=note or result.status_reason,
        provider_event_id=result.provider_event_id,
        provider_status=result.provider_status,
        status_reason=result.status_reason,
        response_payload=result.response_payload,
        action=TransferPayoutEvent.Action.STATUS_SYNC,
    )


@transaction.atomic
def retry_payout_attempt(
    attempt: TransferPayoutAttempt,
    *,
    changed_by=None,
    note: str = "",
) -> TransferPayoutAttempt:
    if attempt.status not in {
        TransferPayoutAttempt.Status.FAILED,
        TransferPayoutAttempt.Status.REVERSED,
    }:
        raise serializers.ValidationError(
            {"payout_attempt_id": "Only failed or reversed payout attempts can be retried."},
        )

    transfer = attempt.transfer
    previous_transfer_status = transfer.status
    transfer.status = Transfer.Status.PROCESSING_PAYOUT
    transfer.payout_status = Transfer.PayoutStatus.RETRYING
    transfer.save(update_fields=("status", "payout_status", "updated_at"))
    if previous_transfer_status != transfer.status:
        TransferStatusEvent.objects.create(
            transfer=transfer,
            from_status=previous_transfer_status,
            to_status=transfer.status,
            changed_by=changed_by,
            note=note or "Retrying payout.",
        )

    record_payout_event(
        transfer=transfer,
        payout_attempt=attempt,
        action=TransferPayoutEvent.Action.RETRY,
        from_payout_status=attempt.status,
        to_payout_status=TransferPayoutAttempt.Status.RETRYING,
        changed_by=changed_by,
        note=note or "Retrying payout.",
    )
    return submit_payout_for_transfer(
        transfer,
        changed_by=changed_by,
        note=note,
        retry_of=attempt,
    )


@transaction.atomic
def reverse_payout_attempt(
    attempt: TransferPayoutAttempt,
    *,
    changed_by=None,
    note: str = "",
) -> TransferPayoutAttempt:
    if attempt.status != TransferPayoutAttempt.Status.PAID_OUT:
        raise serializers.ValidationError(
            {"payout_attempt_id": "Only paid out payout attempts can be reversed."},
        )

    processor = get_payout_processor(attempt.provider.code, provider=attempt.provider)
    result = processor.reverse_payout(attempt=attempt, note=note)
    return apply_payout_attempt_status(
        attempt,
        result.status,
        changed_by=changed_by,
        note=note or result.status_reason,
        provider_status=result.provider_status,
        status_reason=result.status_reason,
        response_payload=result.response_payload,
        action=TransferPayoutEvent.Action.REVERSE,
    )
