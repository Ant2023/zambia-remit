import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.choices import PayoutMethod
from common.models import BaseModel


def generate_transfer_reference() -> str:
    return f"TRF{uuid.uuid4().hex[:12].upper()}"


def generate_payment_reference() -> str:
    return f"PAY{uuid.uuid4().hex[:12].upper()}"


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
        CLEAR = "clear", "Clear"
        FLAGGED = "flagged", "Flagged"
        ON_HOLD = "on_hold", "On hold"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        NEEDS_MORE_INFO = "needs_more_info", "Needs more information"
        NOT_REQUIRED = "not_required", "Not required"
        PENDING = "pending", "Pending"

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
        default=ComplianceStatus.CLEAR,
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


class TransferComplianceFlag(BaseModel):
    class Category(models.TextChoices):
        KYC = "kyc", "KYC"
        LIMIT = "limit", "Limit"
        RISK_RULE = "risk_rule", "Risk rule"
        SANCTIONS = "sanctions", "Sanctions"
        AML = "aml", "AML"
        RECIPIENT = "recipient", "Recipient"
        MANUAL = "manual", "Manual"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.CASCADE,
        related_name="compliance_flags",
    )
    category = models.CharField(max_length=32, choices=Category.choices)
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.OPEN,
    )
    code = models.CharField(max_length=80)
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_transfer_compliance_flags",
        null=True,
        blank=True,
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="resolved_transfer_compliance_flags",
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("transfer", "status")),
            models.Index(fields=("category", "severity")),
            models.Index(fields=("code",)),
        ]

    @property
    def is_open(self) -> bool:
        return self.status in {self.Status.OPEN, self.Status.ACKNOWLEDGED}

    def __str__(self) -> str:
        return f"{self.transfer.reference}: {self.code}"


class TransferComplianceEvent(BaseModel):
    class Action(models.TextChoices):
        NOTE = "note", "Note added"
        HOLD = "hold", "Hold applied"
        REVIEW = "review", "Review started"
        APPROVE = "approve", "Approved"
        REJECT = "reject", "Rejected"
        SCREENING = "screening", "Screening updated"
        AML = "aml", "AML updated"

    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.CASCADE,
        related_name="compliance_events",
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    from_compliance_status = models.CharField(max_length=32, blank=True)
    to_compliance_status = models.CharField(max_length=32, blank=True)
    from_transfer_status = models.CharField(max_length=32, blank=True)
    to_transfer_status = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="transfer_compliance_events",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("transfer", "created_at")),
            models.Index(fields=("action", "created_at")),
            models.Index(fields=("to_compliance_status", "created_at")),
        ]

    def __str__(self) -> str:
        return f"{self.transfer.reference}: {self.action}"


class TransferSanctionsCheck(BaseModel):
    class PartyType(models.TextChoices):
        SENDER = "sender", "Sender"
        RECIPIENT = "recipient", "Recipient"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        CLEAR = "clear", "Clear"
        POSSIBLE_MATCH = "possible_match", "Possible match"
        CONFIRMED_MATCH = "confirmed_match", "Confirmed match"
        ERROR = "error", "Error"
        SKIPPED = "skipped", "Skipped"

    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.CASCADE,
        related_name="sanctions_checks",
    )
    party_type = models.CharField(max_length=24, choices=PartyType.choices)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    screened_name = models.CharField(max_length=180)
    provider_name = models.CharField(max_length=120, default="pending_integration")
    provider_reference = models.CharField(max_length=120, blank=True)
    screening_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    match_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_transfer_sanctions_checks",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ("party_type", "created_at")
        indexes = [
            models.Index(fields=("transfer", "status")),
            models.Index(fields=("party_type", "status")),
            models.Index(fields=("reviewed_at",)),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("transfer", "party_type"),
                name="unique_transfer_sanctions_check_party",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.transfer.reference}: {self.party_type}"


class RecipientVerificationRule(BaseModel):
    class Action(models.TextChoices):
        FLAG = "flag", "Flag"
        HOLD = "hold", "Hold"

    name = models.CharField(max_length=160)
    code = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    corridor = models.ForeignKey(
        "countries.CountryCorridor",
        on_delete=models.CASCADE,
        related_name="recipient_verification_rules",
        null=True,
        blank=True,
    )
    source_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="recipient_verification_rules",
        null=True,
        blank=True,
    )
    destination_country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="recipient_verification_rules",
        null=True,
        blank=True,
    )
    payout_method = models.CharField(
        max_length=24,
        choices=PayoutMethod.choices,
        blank=True,
    )
    min_send_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    action = models.CharField(
        max_length=16,
        choices=Action.choices,
        default=Action.HOLD,
    )
    severity = models.CharField(
        max_length=16,
        choices=TransferComplianceFlag.Severity.choices,
        default=TransferComplianceFlag.Severity.MEDIUM,
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=("is_active", "destination_country")),
            models.Index(fields=("corridor", "is_active")),
            models.Index(fields=("source_currency", "is_active")),
            models.Index(fields=("payout_method", "is_active")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_send_amount__isnull=True)
                | models.Q(min_send_amount__gt=0),
                name="recipient_verification_rule_min_send_gt_0_or_null",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TransferAmlRule(BaseModel):
    class RuleType(models.TextChoices):
        LARGE_TRANSFER = "large_transfer", "Large transfer amount"
        DAILY_VOLUME = "daily_volume", "Daily sender volume"
        VELOCITY_COUNT = "velocity_count", "Velocity transfer count"
        VELOCITY_VOLUME = "velocity_volume", "Velocity transfer volume"

    class Action(models.TextChoices):
        FLAG = "flag", "Flag"
        HOLD = "hold", "Hold"

    name = models.CharField(max_length=160)
    code = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    rule_type = models.CharField(max_length=40, choices=RuleType.choices)
    corridor = models.ForeignKey(
        "countries.CountryCorridor",
        on_delete=models.CASCADE,
        related_name="transfer_aml_rules",
        null=True,
        blank=True,
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transfer_aml_rules",
        null=True,
        blank=True,
    )
    source_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="transfer_aml_rules",
        null=True,
        blank=True,
    )
    destination_country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="transfer_aml_rules",
        null=True,
        blank=True,
    )
    payout_method = models.CharField(
        max_length=24,
        choices=PayoutMethod.choices,
        blank=True,
    )
    threshold_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Used by amount and volume monitoring rules.",
    )
    transfer_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Used by velocity count monitoring rules.",
    )
    window_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Used by velocity monitoring rules.",
    )
    action = models.CharField(
        max_length=16,
        choices=Action.choices,
        default=Action.FLAG,
    )
    severity = models.CharField(
        max_length=16,
        choices=TransferComplianceFlag.Severity.choices,
        default=TransferComplianceFlag.Severity.MEDIUM,
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=("is_active", "rule_type")),
            models.Index(fields=("corridor", "is_active")),
            models.Index(fields=("sender", "is_active")),
            models.Index(fields=("source_currency", "is_active")),
            models.Index(fields=("destination_country", "is_active")),
            models.Index(fields=("payout_method", "is_active")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(threshold_amount__isnull=True)
                | models.Q(threshold_amount__gt=0),
                name="aml_rule_threshold_gt_0_or_null",
            ),
            models.CheckConstraint(
                condition=models.Q(transfer_count__isnull=True)
                | models.Q(transfer_count__gt=0),
                name="aml_rule_transfer_count_gt_0_or_null",
            ),
            models.CheckConstraint(
                condition=models.Q(window_minutes__isnull=True)
                | models.Q(window_minutes__gt=0),
                name="aml_rule_window_gt_0_or_null",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TransferLimitRule(BaseModel):
    class Period(models.TextChoices):
        PER_TRANSFER = "per_transfer", "Per transfer"
        DAILY = "daily", "Daily"
        MONTHLY = "monthly", "Monthly"

    class Action(models.TextChoices):
        FLAG = "flag", "Flag"
        HOLD = "hold", "Hold"

    name = models.CharField(max_length=160)
    code = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    corridor = models.ForeignKey(
        "countries.CountryCorridor",
        on_delete=models.CASCADE,
        related_name="transfer_limit_rules",
        null=True,
        blank=True,
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transfer_limit_rules",
        null=True,
        blank=True,
    )
    source_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="transfer_limit_rules",
        null=True,
        blank=True,
    )
    payout_method = models.CharField(
        max_length=24,
        choices=PayoutMethod.choices,
        blank=True,
    )
    period = models.CharField(max_length=24, choices=Period.choices)
    max_send_amount = models.DecimalField(max_digits=12, decimal_places=2)
    action = models.CharField(
        max_length=16,
        choices=Action.choices,
        default=Action.FLAG,
    )
    severity = models.CharField(
        max_length=16,
        choices=TransferComplianceFlag.Severity.choices,
        default=TransferComplianceFlag.Severity.MEDIUM,
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=("is_active", "period")),
            models.Index(fields=("corridor", "is_active")),
            models.Index(fields=("sender", "is_active")),
            models.Index(fields=("source_currency", "is_active")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_send_amount__gt=0),
                name="transfer_limit_rule_max_send_gt_0",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TransferRiskRule(BaseModel):
    class RuleType(models.TextChoices):
        HIGH_AMOUNT = "high_amount", "High amount"
        FIRST_TRANSFER = "first_transfer", "First transfer"
        RAPID_REPEAT = "rapid_repeat", "Rapid repeat transfer"
        INCOMPLETE_PROFILE = "incomplete_profile", "Incomplete sender profile"
        UNVERIFIED_KYC = "unverified_kyc", "Unverified KYC"
        DESTINATION_METHOD = "destination_method", "Destination or method rule"

    class Action(models.TextChoices):
        FLAG = "flag", "Flag"
        HOLD = "hold", "Hold"

    name = models.CharField(max_length=160)
    code = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    rule_type = models.CharField(max_length=40, choices=RuleType.choices)
    corridor = models.ForeignKey(
        "countries.CountryCorridor",
        on_delete=models.CASCADE,
        related_name="transfer_risk_rules",
        null=True,
        blank=True,
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transfer_risk_rules",
        null=True,
        blank=True,
    )
    source_currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="transfer_risk_rules",
        null=True,
        blank=True,
    )
    destination_country = models.ForeignKey(
        "countries.Country",
        on_delete=models.PROTECT,
        related_name="transfer_risk_rules",
        null=True,
        blank=True,
    )
    payout_method = models.CharField(
        max_length=24,
        choices=PayoutMethod.choices,
        blank=True,
    )
    threshold_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Used by high amount rules.",
    )
    repeat_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Used by rapid repeat rules.",
    )
    window_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Used by rapid repeat rules.",
    )
    action = models.CharField(
        max_length=16,
        choices=Action.choices,
        default=Action.FLAG,
    )
    severity = models.CharField(
        max_length=16,
        choices=TransferComplianceFlag.Severity.choices,
        default=TransferComplianceFlag.Severity.MEDIUM,
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=("is_active", "rule_type")),
            models.Index(fields=("corridor", "is_active")),
            models.Index(fields=("sender", "is_active")),
            models.Index(fields=("source_currency", "is_active")),
            models.Index(fields=("destination_country", "is_active")),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(threshold_amount__isnull=True)
                | models.Q(threshold_amount__gt=0),
                name="risk_rule_threshold_gt_0_or_null",
            ),
            models.CheckConstraint(
                condition=models.Q(repeat_count__isnull=True)
                | models.Q(repeat_count__gt=0),
                name="risk_rule_repeat_count_gt_0_or_null",
            ),
            models.CheckConstraint(
                condition=models.Q(window_minutes__isnull=True)
                | models.Q(window_minutes__gt=0),
                name="risk_rule_window_gt_0_or_null",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TransferPaymentInstruction(BaseModel):
    class PaymentMethod(models.TextChoices):
        DEBIT_CARD = "debit_card", "Debit card"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PENDING_AUTHORIZATION = "pending_authorization", "Pending authorization"
        AUTHORIZED = "authorized", "Authorized"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"
        REFUNDED = "refunded", "Refunded"
        REQUIRES_REVIEW = "requires_review", "Requires review"
        EXPIRED = "expired", "Expired"

    transfer = models.ForeignKey(
        Transfer,
        on_delete=models.CASCADE,
        related_name="payment_instructions",
    )
    payment_method = models.CharField(max_length=32, choices=PaymentMethod.choices)
    provider_name = models.CharField(max_length=120, default="mock")
    provider_reference = models.CharField(
        max_length=64,
        unique=True,
        default=generate_payment_reference,
        editable=False,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.ForeignKey(
        "countries.Currency",
        on_delete=models.PROTECT,
        related_name="payment_instructions",
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    instructions = models.JSONField(default=dict, blank=True)
    status_reason = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    authorized_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("transfer", "status")),
            models.Index(fields=("provider_name", "provider_reference")),
            models.Index(fields=("expires_at",)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_instruction_amount_gt_0",
            ),
        ]

    @property
    def is_completed(self) -> bool:
        return self.status == self.Status.PAID

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            self.Status.PAID,
            self.Status.CANCELLED,
            self.Status.FAILED,
            self.Status.REVERSED,
            self.Status.REFUNDED,
            self.Status.EXPIRED,
        }

    def mark_paid(self, *, reason: str = "") -> None:
        self.status = self.Status.PAID
        if reason:
            self.status_reason = reason
        self.completed_at = timezone.now()
        self.save(
            update_fields=("status", "status_reason", "completed_at", "updated_at"),
        )

    def __str__(self) -> str:
        return f"{self.transfer.reference} {self.payment_method}"


class TransferPaymentWebhookEvent(BaseModel):
    class ProcessingStatus(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    payment_instruction = models.ForeignKey(
        TransferPaymentInstruction,
        on_delete=models.SET_NULL,
        related_name="webhook_events",
        null=True,
        blank=True,
    )
    provider_name = models.CharField(max_length=120)
    provider_event_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=120)
    provider_reference = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    processing_status = models.CharField(
        max_length=24,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.RECEIVED,
    )
    processing_message = models.TextField(blank=True)
    resulting_payment_status = models.CharField(max_length=32, blank=True)
    event_created_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("provider_name", "provider_reference")),
            models.Index(fields=("processing_status", "created_at")),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("provider_name", "provider_event_id"),
                name="payment_webhook_provider_event_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider_name}:{self.provider_event_id}"


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
