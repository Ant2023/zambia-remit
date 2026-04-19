import uuid

from django.conf import settings
from django.db import models

from common.choices import PayoutMethod
from common.models import BaseModel


def generate_transfer_reference() -> str:
    return f"TRF{uuid.uuid4().hex[:12].upper()}"


class Transfer(BaseModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUOTE_CREATED = "quote_created", "Quote created"
        AWAITING_FUNDING = "awaiting_funding", "Awaiting funding"
        FUNDING_RECEIVED = "funding_received", "Funding received"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        PROCESSING_PAYOUT = "processing_payout", "Processing payout"
        PAID_OUT = "paid_out", "Paid out"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected"
        REFUNDED = "refunded", "Refunded"

    class FundingStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PENDING = "pending", "Pending"
        RECEIVED = "received", "Received"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    class ComplianceStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "Not required"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        NEEDS_MORE_INFO = "needs_more_info", "Needs more information"

    class PayoutStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    reference = models.CharField(
        max_length=32,
        unique=True,
        default=generate_transfer_reference,
        editable=False,
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transfers",
    )
    recipient = models.ForeignKey(
        "recipients.Recipient",
        on_delete=models.PROTECT,
        related_name="transfers",
    )
    quote = models.OneToOneField(
        "quotes.Quote",
        on_delete=models.PROTECT,
        related_name="transfer",
    )
    source_country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="source_transfers",
    )
    destination_country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="destination_transfers",
    )
    source_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="source_transfers",
    )
    destination_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="destination_transfers",
    )
    payout_method = models.CharField(max_length=24, choices=PayoutMethod.choices)
    send_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8)
    receive_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.AWAITING_FUNDING,
    )
    funding_status = models.CharField(
        max_length=32,
        choices=FundingStatus.choices,
        default=FundingStatus.PENDING,
    )
    compliance_status = models.CharField(
        max_length=32,
        choices=ComplianceStatus.choices,
        default=ComplianceStatus.PENDING,
    )
    payout_status = models.CharField(
        max_length=32,
        choices=PayoutStatus.choices,
        default=PayoutStatus.NOT_STARTED,
    )
    reason_for_transfer = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("sender", "status")),
            models.Index(fields=("status", "created_at")),
            models.Index(fields=("funding_status",)),
            models.Index(fields=("compliance_status",)),
            models.Index(fields=("payout_status",)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(send_amount__gt=0),
                name="transfer_send_amount_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(fee_amount__gte=0),
                name="transfer_fee_amount_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(exchange_rate__gt=0),
                name="transfer_exchange_rate_gt_0",
            ),
            models.CheckConstraint(
                condition=models.Q(receive_amount__gt=0),
                name="transfer_receive_amount_gt_0",
            ),
        ]

    def __str__(self) -> str:
        return self.reference


class TransferStatusEvent(BaseModel):
    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.CASCADE,
        related_name="status_events",
    )
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="transfer_status_events",
        null=True,
        blank=True,
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("transfer", "created_at")),
            models.Index(fields=("to_status", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.transfer.reference}: {self.from_status} -> {self.to_status}"
