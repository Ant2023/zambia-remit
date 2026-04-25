from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.accounts.models import SenderProfile
from apps.quotes.models import Quote

from .models import (
    Transfer,
    TransferComplianceFlag,
    TransferNotification,
    TransferPaymentInstruction,
    TransferPayoutAttempt,
)


MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.01")

PAYMENT_FAILURE_STATUSES = {
    TransferPaymentInstruction.Status.FAILED,
    TransferPaymentInstruction.Status.CANCELLED,
    TransferPaymentInstruction.Status.EXPIRED,
    TransferPaymentInstruction.Status.REVERSED,
    TransferPaymentInstruction.Status.REFUNDED,
}

PAYOUT_FAILURE_STATUSES = {
    TransferPayoutAttempt.Status.FAILED,
    TransferPayoutAttempt.Status.REVERSED,
}

ACTIVE_TRANSFER_STATUSES = {
    Transfer.Status.AWAITING_FUNDING,
    Transfer.Status.FUNDING_RECEIVED,
    Transfer.Status.UNDER_REVIEW,
    Transfer.Status.APPROVED,
    Transfer.Status.PROCESSING_PAYOUT,
    Transfer.Status.PAID_OUT,
}

EXCEPTION_TRANSFER_STATUSES = {
    Transfer.Status.FAILED,
    Transfer.Status.REJECTED,
    Transfer.Status.REFUNDED,
    Transfer.Status.CANCELLED,
}


def default_report_window() -> tuple[datetime, datetime]:
    end_at = timezone.now()
    return end_at - timedelta(days=30), end_at


def make_report_window(start_date=None, end_date=None) -> tuple[datetime, datetime]:
    default_start, default_end = default_report_window()
    if start_date is None and end_date is None:
        return default_start, default_end

    current_timezone = timezone.get_current_timezone()
    start_at = (
        timezone.make_aware(datetime.combine(start_date, time.min), current_timezone)
        if start_date
        else default_start
    )
    end_at = (
        timezone.make_aware(
            datetime.combine(end_date + timedelta(days=1), time.min),
            current_timezone,
        )
        if end_date
        else default_end
    )
    return start_at, end_at


def decimal_string(value, quant: Decimal = MONEY_QUANT) -> str:
    if value is None:
        value = Decimal("0")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return str(value.quantize(quant))


def percentage(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00"
    return decimal_string(
        (Decimal(numerator) / Decimal(denominator)) * Decimal("100"),
        RATE_QUANT,
    )


def window_filter(start_at: datetime, end_at: datetime) -> dict:
    return {"created_at__gte": start_at, "created_at__lt": end_at}


def choice_counts(queryset, field_name: str, choices) -> list[dict]:
    raw_counts = {
        item[field_name]: item["count"]
        for item in queryset.values(field_name).annotate(count=Count("id"))
    }
    return [
        {
            "value": value,
            "label": label,
            "count": raw_counts.get(value, 0),
        }
        for value, label in choices
    ]


def money_breakdown(queryset, *, amount_field: str, currency_field: str) -> list[dict]:
    currency_path = f"{currency_field}__code"
    return [
        {
            "currency": item[currency_path],
            "count": item["count"],
            "total": decimal_string(item["total"]),
        }
        for item in queryset.values(currency_path)
        .annotate(count=Count("id"), total=Sum(amount_field))
        .order_by(currency_path)
    ]


def daily_transfer_volume(transfers) -> list[dict]:
    return [
        {
            "date": item["day"].isoformat() if item["day"] else "",
            "currency": item["source_currency__code"],
            "transaction_count": item["transaction_count"],
            "send_amount_total": decimal_string(item["send_amount_total"]),
            "fee_amount_total": decimal_string(item["fee_amount_total"]),
        }
        for item in transfers.annotate(day=TruncDate("created_at"))
        .values("day", "source_currency__code")
        .annotate(
            transaction_count=Count("id"),
            send_amount_total=Sum("send_amount"),
            fee_amount_total=Sum("fee_amount"),
        )
        .order_by("day", "source_currency__code")
    ]


def funnel_step(label: str, value: str, count: int, previous_count: int, first_count: int):
    return {
        "label": label,
        "value": value,
        "count": count,
        "conversion_from_previous_percent": percentage(count, previous_count),
        "conversion_from_start_percent": percentage(count, first_count),
    }


def build_funnel_report(
    *,
    quotes,
    transfers,
    payment_instructions,
    payout_attempts,
) -> list[dict]:
    steps = [
        ("Quotes created", "quotes_created", quotes.count()),
        ("Transfers created", "transfers_created", transfers.count()),
        (
            "Payment instructions created",
            "payment_instructions_created",
            payment_instructions.count(),
        ),
        (
            "Payments received",
            "payments_received",
            payment_instructions.filter(
                status=TransferPaymentInstruction.Status.PAID,
            ).count(),
        ),
        (
            "Payouts submitted",
            "payouts_submitted",
            payout_attempts.filter(
                status__in={
                    TransferPayoutAttempt.Status.SUBMITTED,
                    TransferPayoutAttempt.Status.PROCESSING,
                    TransferPayoutAttempt.Status.PAID_OUT,
                },
            ).count(),
        ),
        (
            "Payouts completed",
            "payouts_completed",
            payout_attempts.filter(
                status=TransferPayoutAttempt.Status.PAID_OUT,
            ).count(),
        ),
        (
            "Transfers completed",
            "transfers_completed",
            transfers.filter(status=Transfer.Status.COMPLETED).count(),
        ),
    ]
    first_count = steps[0][2] if steps else 0
    previous_count = first_count
    funnel = []
    for label, value, count in steps:
        funnel.append(funnel_step(label, value, count, previous_count, first_count))
        previous_count = count
    return funnel


def build_operations_report(*, start_at: datetime, end_at: datetime) -> dict:
    transfers = Transfer.objects.filter(**window_filter(start_at, end_at))
    quotes = Quote.objects.filter(**window_filter(start_at, end_at))
    payment_instructions = TransferPaymentInstruction.objects.filter(
        **window_filter(start_at, end_at),
    )
    payout_attempts = TransferPayoutAttempt.objects.filter(
        **window_filter(start_at, end_at),
    )
    kyc_submissions = SenderProfile.objects.filter(
        kyc_submitted_at__gte=start_at,
        kyc_submitted_at__lt=end_at,
    )
    kyc_reviews = SenderProfile.objects.filter(
        kyc_reviewed_at__gte=start_at,
        kyc_reviewed_at__lt=end_at,
    )

    total_transfers = transfers.count()
    completed_transfers = transfers.filter(status=Transfer.Status.COMPLETED).count()
    payment_count = payment_instructions.count()
    failed_payment_count = payment_instructions.filter(
        status__in=PAYMENT_FAILURE_STATUSES,
    ).count()
    payout_count = payout_attempts.count()
    failed_payout_count = payout_attempts.filter(
        status__in=PAYOUT_FAILURE_STATUSES,
    ).count()
    kyc_submitted_count = kyc_submissions.count()
    kyc_verified_count = kyc_reviews.filter(
        kyc_status=SenderProfile.KycStatus.VERIFIED,
    ).count()

    fee_aggregate = transfers.aggregate(
        total_fee_amount=Sum("fee_amount"),
        average_fee_amount=Avg("fee_amount"),
    )
    funded_fee_aggregate = transfers.filter(
        funding_status=Transfer.FundingStatus.RECEIVED,
    ).aggregate(total_fee_amount=Sum("fee_amount"))

    return {
        "window": {
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "generated_at": timezone.now().isoformat(),
        },
        "transaction_volume": {
            "created_count": total_transfers,
            "completed_count": completed_transfers,
            "completion_rate_percent": percentage(
                completed_transfers,
                total_transfers,
            ),
            "send_amount_by_currency": money_breakdown(
                transfers,
                amount_field="send_amount",
                currency_field="source_currency",
            ),
            "receive_amount_by_currency": money_breakdown(
                transfers,
                amount_field="receive_amount",
                currency_field="destination_currency",
            ),
            "by_status": choice_counts(transfers, "status", Transfer.Status.choices),
            "daily": daily_transfer_volume(transfers),
        },
        "revenue": {
            "fee_amount_by_currency": money_breakdown(
                transfers,
                amount_field="fee_amount",
                currency_field="source_currency",
            ),
            "total_fee_amount": decimal_string(fee_aggregate["total_fee_amount"]),
            "realized_fee_amount": decimal_string(
                funded_fee_aggregate["total_fee_amount"],
            ),
            "average_fee_amount": decimal_string(
                fee_aggregate["average_fee_amount"],
            ),
        },
        "failed_payment_rates": {
            "payment_instruction_count": payment_count,
            "failed_count": failed_payment_count,
            "failed_rate_percent": percentage(failed_payment_count, payment_count),
            "by_status": choice_counts(
                payment_instructions,
                "status",
                TransferPaymentInstruction.Status.choices,
            ),
        },
        "failed_payout_rates": {
            "payout_attempt_count": payout_count,
            "failed_count": failed_payout_count,
            "failed_rate_percent": percentage(failed_payout_count, payout_count),
            "by_status": choice_counts(
                payout_attempts,
                "status",
                TransferPayoutAttempt.Status.choices,
            ),
        },
        "kyc_completion": {
            "submitted_count": kyc_submitted_count,
            "verified_count": kyc_verified_count,
            "completion_rate_percent": percentage(
                kyc_verified_count,
                kyc_submitted_count,
            ),
            "status_counts": choice_counts(
                SenderProfile.objects.filter(created_at__lt=end_at),
                "kyc_status",
                SenderProfile.KycStatus.choices,
            ),
        },
        "funnel": build_funnel_report(
            quotes=quotes,
            transfers=transfers,
            payment_instructions=payment_instructions,
            payout_attempts=payout_attempts,
        ),
        "admin_reports": {
            "active_transfer_count": transfers.filter(
                status__in=ACTIVE_TRANSFER_STATUSES,
            ).count(),
            "exception_transfer_count": transfers.filter(
                status__in=EXCEPTION_TRANSFER_STATUSES,
            ).count(),
            "open_compliance_flag_count": TransferComplianceFlag.objects.filter(
                status__in={
                    TransferComplianceFlag.Status.OPEN,
                    TransferComplianceFlag.Status.ACKNOWLEDGED,
                },
                created_at__lt=end_at,
            ).count(),
            "pending_notification_count": TransferNotification.objects.filter(
                status=TransferNotification.Status.PENDING,
                created_at__lt=end_at,
            ).count(),
            "notification_status_counts": choice_counts(
                TransferNotification.objects.filter(**window_filter(start_at, end_at)),
                "status",
                TransferNotification.Status.choices,
            ),
        },
    }
